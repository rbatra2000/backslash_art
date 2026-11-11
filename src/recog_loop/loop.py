"""The recursive backwards loop. Writes runs/<id>/{run.json, events.jsonl, step_XX/...}."""
import json
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps

from . import scoring
from .config import ROOT
from .editor import KleinEditor, build_reverse_prompt
from .reader import read_image


class Events:
    """Append-only JSONL log that the UI follows live."""

    def __init__(self, path: Path):
        self.path = path

    def emit(self, type_: str, step: int | None = None, **data):
        line = {"t": round(time.time(), 2), "type": type_, "step": step, **data}
        with self.path.open("a") as f:
            f.write(json.dumps(line) + "\n")


def _git_state() -> dict:
    def run(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain"))}


def _normalise(src: Path, dst: Path, max_edge: int):
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    img.thumbnail((max_edge, max_edge))
    img.save(dst, "PNG")


def _banned_op(ops_history: list[str], limit: int) -> str | None:
    if len(ops_history) >= limit and len(set(ops_history[-limit:])) == 1:
        return ops_history[-1]
    return None


def _composite(c: dict, w: dict, sat: float) -> float:
    disp = min(c["displacement"] / sat, 1.0)
    return (w["legibility"] * c["legibility"] + w["inheritance"] * c["inheritance"]
            + w["displacement"] * disp) / sum(w.values())


def run(image: Path, steps: int, cfg: dict, lex: dict, keys: dict, run_id: str | None = None) -> Path:
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ev = Events(run_dir / "events.jsonl")
    g, w = cfg["gates"], cfg["score_weights"]
    sat = g.get("displacement_saturation", 0.5)
    model, ak = cfg["models"]["reader"], keys["ANTHROPIC_API_KEY"]
    editor = KleinEditor(keys["BFL_API_KEY"], cfg["image"]["max_edge"], cfg["image"]["output_format"])
    n_cand = cfg["run"]["candidates"]

    (run_dir / "run.json").write_text(json.dumps({
        "run_id": run_id, "image": str(image), "steps": steps, "config": cfg,
        "lexicon_ops": list(lex), "git": _git_state(), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2))
    ev.emit("run_start", run_id=run_id, steps=steps, candidates=n_cand)

    current = run_dir / "step_01" / "input.png"
    current.parent.mkdir(exist_ok=True)
    _normalise(image, current, cfg["image"]["max_edge"])
    anchor = current
    history_readings: list[dict] = []
    ops_history: list[str] = []

    for t in range(1, steps + 1):
        sd = run_dir / f"step_{t:02d}"
        sd.mkdir(exist_ok=True)
        if t > 1:
            shutil.copy(current, sd / "input.png")
        inp = sd / "input.png"
        ev.emit("step_start", t, input=str(inp.relative_to(run_dir)))

        # 1. READ (stateless; the only history it gets is a ban on over-repeated operations)
        banned = _banned_op(ops_history, g["max_same_op_in_row"])
        avail = {k: v for k, v in lex.items() if k != banned}
        ev.emit("status", t, text="reading image" + (f" (excluding {banned}, used {g['max_same_op_in_row']}x in a row)" if banned else ""))
        reading = read_image(inp, avail, cfg, ak)
        op = reading["operation"]["name"]
        ops_history.append(op)
        history_readings.append(reading)
        ev.emit("reading", t, readings=reading["readings"], scale=reading["scale_estimate"])
        ev.emit("hypothesis", t, formation=reading["formation"], operation=reading["operation"], banned=banned)

        # 2. PROMPT
        prompt = build_reverse_prompt(op, lex[op], reading)
        ev.emit("prompt", t, text=prompt)

        # 3. GENERATE candidates in parallel
        ev.emit("status", t, text=f"generating 0/{n_cand}")
        cands: list[dict] = [{"index": k, "seed": cfg["run"]["base_seed"] + t * 100 + k} for k in range(n_cand)]

        def gen(c):
            path = sd / f"cand_{c['index']}.png"
            meta = editor.edit(inp, prompt, c["seed"], path)
            return c["index"], path, meta

        done = 0
        with ThreadPoolExecutor(max_workers=n_cand) as pool:
            futs = [pool.submit(gen, c) for c in cands]
            for f in as_completed(futs):
                try:
                    k, path, meta = f.result()
                    cands[k].update(file=path.name, meta=meta)
                    done += 1
                    ev.emit("candidate", t, index=k, file=str(path.relative_to(run_dir)))
                    ev.emit("status", t, text=f"generating {done}/{n_cand}")
                except Exception as e:  # keep going with the candidates that worked
                    ev.emit("error", t, text=f"candidate generation failed: {e}")
        ok = [c for c in cands if "file" in c]
        if not ok:
            raise RuntimeError(f"step {t}: all candidate generations failed")

        # 4. SCORE (each call is blind and stateless)
        ev.emit("status", t, text=f"scoring {len(ok)} candidates (blind judges)")

        def score(c):
            cp = sd / c["file"]
            j = scoring.judge(inp, cp, op, lex[op], ak, model)
            a = j if anchor == inp else scoring.judge(anchor, cp, op, lex[op], ak, model)
            r = read_image(cp, lex, cfg, ak)  # blind re-read of the candidate: its reading distribution
            return c["index"], j, a, r

        with ThreadPoolExecutor(max_workers=len(ok)) as pool:
            results = list(pool.map(score, ok))
        for k, j, a, r in results:
            cands[k].update(
                legibility=j["legibility"]["score"], legibility_reason=j["legibility"]["reasoning"],
                inheritance=j["inheritance"]["score"], inheritance_reason=j["inheritance"]["reasoning"],
                anchor=a["inheritance"]["score"], anchor_reason=a["inheritance"]["reasoning"],
                cand_reading=r)

        # displacement: align labels from this step's input, each candidate, and recent history
        recent = history_readings[-(g["no_repeat_window"] + 1):-1]
        sets = {"input": [x["label"] for x in reading["readings"]]}
        for c in ok:
            sets[f"cand{c['index']}"] = [x["label"] for x in c["cand_reading"]["readings"]]
        for i, h in enumerate(recent):
            sets[f"hist{i}"] = [x["label"] for x in h["readings"]]
        cat = scoring.align_categories(sets, ak, model)
        p_in = scoring.to_distribution(reading, cat)
        p_hist = [scoring.to_distribution(h, cat) for h in recent]
        for c in ok:
            p = scoring.to_distribution(c["cand_reading"], cat)
            c["distribution"] = p
            c["displacement"] = round(scoring.js_divergence(p_in, p), 4)
            c["entropy_change"] = round(scoring.entropy(p) - scoring.entropy(p_in), 4)
            fails = []
            if c["legibility"] < g["legibility_floor"]: fails.append("legibility below floor")
            if c["inheritance"] < g["inheritance_floor"]: fails.append("inheritance below floor")
            if c["anchor"] < g["anchor_floor"]: fails.append("lost the original image (anchor)")
            if c["displacement"] < g["displacement_min"]: fails.append("reading barely moved")
            if any(scoring.js_divergence(p, ph) < g["displacement_min"] for ph in p_hist):
                fails.append("reading cycled back to a recent step")
            c["gate_fails"] = fails
            c["composite"] = round(_composite(c, w, sat), 4)
            ev.emit("scores", t, index=c["index"], **{k: c[k] for k in (
                "legibility", "legibility_reason", "inheritance", "inheritance_reason", "anchor",
                "anchor_reason", "displacement", "entropy_change", "composite", "gate_fails", "distribution")},
                cand_readings=c["cand_reading"]["readings"])

        # 5. SELECT
        passing = [c for c in ok if not c["gate_fails"]]
        pool_ = passing or ok
        best = max(pool_, key=lambda c: c["composite"])
        why = ("highest composite among candidates passing all gates" if passing
               else "NO candidate passed all gates; took highest composite anyway (flagged)")
        shutil.copy(sd / best["file"], sd / "selected.png")
        current = sd / "selected.png"
        ev.emit("selected", t, index=best["index"], file=str(current.relative_to(run_dir)), reason=why,
                gates_passed=bool(passing))
        (sd / "record.json").write_text(json.dumps({
            "step": t, "reading": reading, "banned_op": banned, "operation": op, "prompt": prompt,
            "candidates": cands, "selected": best["index"], "selection_reason": why,
            "gates_passed": bool(passing)}, indent=2))
        ev.emit("step_end", t)

    ev.emit("run_end", None)
    return run_dir
