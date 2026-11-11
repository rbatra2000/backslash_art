"""Backwards loop: plan, undo with Klein, repeat. Writes runs/<timestamp>/."""
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

    for t in range(1, steps + 1):
        sd = run_dir / f"step_{t:02d}"
        sd.mkdir(exist_ok=True)
        inp = sd / "input.png"
        if t > 1:
            inp.write_bytes(current.read_bytes())
        ev.emit("step_start", t, input=str(inp.relative_to(run_dir)))

        # 1. PLAN: read the image, hypothesize formation, choose the operation to undo
        ev.emit("status", t, text="reading image")
        plan = read_image(inp, lex, cfg, ak)
        op = plan["operation"]["name"]
        ev.emit("reading", t, identity=plan["identity"], scale=plan["scale_estimate"])
        ev.emit("hypothesis", t, formation=plan["formation"], operation=plan["operation"])

        # 2. PROMPT, 3. GENERATE one image
        prompt = build_reverse_prompt(op, lex[op], plan, cfg["image"]["strength"])
        ev.emit("prompt", t, text=prompt)
        ev.emit("status", t, text="generating image")
        seed = cfg["run"]["base_seed"] + t * 100
        out = sd / "result.png"
        meta = editor.edit(inp, prompt, seed, out)
        ev.emit("result", t, file=str(out.relative_to(run_dir)))

        (sd / "record.json").write_text(json.dumps({
            "step": t, "operation": op, "plan": plan, "prompt": prompt, "seed": seed, "editor_meta": meta}, indent=2))
        current = out
        ev.emit("step_end", t)

    ev.emit("status", None, text="reading final image")
    final = read_image(current, lex, cfg, ak)
    (run_dir / "final.json").write_text(json.dumps(final, indent=2))
    ev.emit("final", None, identity=final["identity"], file=str(current.relative_to(run_dir)))
    ev.emit("run_end", None)
    return run_dir
