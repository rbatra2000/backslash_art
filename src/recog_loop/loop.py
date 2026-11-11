"""Backwards loop: one image per step, then a blind re-read. Writes runs/<timestamp>/."""
import json
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageOps

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


def _history_context(done: list[dict]) -> str | None:
    """Planner-only context: what has already been undone, so each step reaches further back."""
    if not done:
        return None
    lines = [f"{i}. {d['op']}: {d['process']}" for i, d in enumerate(done, 1)]
    return ("Already undone, in order:\n" + "\n".join(lines) +
            "\nThis image is the sample after those. Choose the most likely process for it as it looks now; "
            "repeats are fine; don't name products already gone.")


def run(image: Path, steps: int, cfg: dict, lex: dict, keys: dict, run_id: str | None = None) -> Path:
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ev = Events(run_dir / "events.jsonl")
    model, ak = cfg["models"]["reader"], keys["ANTHROPIC_API_KEY"]
    editor = KleinEditor(keys["BFL_API_KEY"], cfg["image"]["max_edge"], cfg["image"]["output_format"])

    (run_dir / "run.json").write_text(json.dumps({
        "run_id": run_id, "image": str(image), "steps": steps, "config": cfg,
        "lexicon_ops": list(lex), "git": _git_state(), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2))
    ev.emit("run_start", run_id=run_id, steps=steps)

    current = run_dir / "step_01" / "input.png"
    current.parent.mkdir(exist_ok=True)
    _normalise(image, current, cfg["image"]["max_edge"])
    done_steps: list[dict] = []         # planner history: {op, process}
    prev_blind: dict | None = None      # blind re-read of the previous output = this step's "before" reading

    for t in range(1, steps + 1):
        sd = run_dir / f"step_{t:02d}"
        sd.mkdir(exist_ok=True)
        inp = sd / "input.png"
        if t > 1:
            inp.write_bytes(current.read_bytes())
        ev.emit("step_start", t, input=str(inp.relative_to(run_dir)))

        # 1. PLAN: read the image, hypothesize formation, choose the operation to undo
        ev.emit("status", t, text="reading image")
        plan = read_image(inp, lex, cfg, ak, prior_context=_history_context(done_steps))
        op = plan["operation"]["name"]
        # The "before" reading shown must be blind. Step 1's planner has no context so it is blind;
        # later steps reuse the blind re-read already made of this exact image.
        before = plan if prev_blind is None else prev_blind
        ev.emit("reading", t, readings=before["readings"], scale=before["scale_estimate"])
        ev.emit("hypothesis", t, formation=plan["formation"], operation=plan["operation"])

        # 2. PROMPT, 3. GENERATE one image
        prompt = build_reverse_prompt(op, lex[op], plan, cfg["image"]["strength"])
        ev.emit("prompt", t, text=prompt)
        ev.emit("status", t, text="generating image")
        seed = cfg["run"]["base_seed"] + t * 100
        out = sd / "result.png"
        meta = editor.edit(inp, prompt, seed, out)
        ev.emit("result", t, file=str(out.relative_to(run_dir)))

        # 4. RE-READ the result blind (no history); this is the "after" reading and the next step's "before"
        ev.emit("status", t, text="re-reading result")
        after = read_image(out, lex, cfg, ak)
        ev.emit("after", t, after_readings=after["readings"])

        (sd / "record.json").write_text(json.dumps({
            "step": t, "operation": op, "plan": plan, "before_reading": before,
            "prompt": prompt, "seed": seed, "editor_meta": meta,
            "after_reading": after}, indent=2))
        prev_blind = after
        current = out
        done_steps.append({"op": op, "process": plan["formation"]["process"]})
        ev.emit("step_end", t)

    ev.emit("run_end", None)
    return run_dir
