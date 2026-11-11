import argparse
import json

from .config import load_config, load_env, load_lexicon


def main():
    p = argparse.ArgumentParser(prog="recog_loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="run the reader once on an image and print the result")
    r.add_argument("--image", required=True)
    s = sub.add_parser("step", help="one step: read, build reverse prompt, generate candidates")
    s.add_argument("--image", required=True)
    s.add_argument("--out", default=None, help="output dir (default runs/<timestamp>/step_01)")
    rn = sub.add_parser("run", help="run the full backwards loop")
    rn.add_argument("--image", required=True)
    rn.add_argument("--steps", type=int, default=None, help="default from config.yaml")
    rn.add_argument("--run-id", default=None)
    sv = sub.add_parser("serve", help="live + replay UI on localhost")
    sv.add_argument("--port", type=int, default=5000)
    args = p.parse_args()

    if args.cmd == "read":
        from .reader import read_image
        keys = load_env(required=["ANTHROPIC_API_KEY"])
        out = read_image(args.image, load_lexicon(), load_config(), keys["ANTHROPIC_API_KEY"])
        print(json.dumps(out, indent=2))

    if args.cmd == "serve":
        from .serve import main as serve_main
        serve_main(args.port)

    if args.cmd == "run":
        from pathlib import Path
        from .loop import run
        cfg = load_config()
        d = run(Path(args.image), args.steps or cfg["run"]["steps"], cfg, load_lexicon(), load_env(), args.run_id)
        print(f"done: {d}")

    if args.cmd == "step":
        import time
        from pathlib import Path
        from .config import ROOT
        from .editor import KleinEditor, build_reverse_prompt
        from .reader import read_image
        cfg, lex = load_config(), load_lexicon()
        keys = load_env()
        out_dir = Path(args.out) if args.out else ROOT / "runs" / time.strftime("%Y%m%d-%H%M%S") / "step_01"
        out_dir.mkdir(parents=True, exist_ok=True)
        reading = read_image(args.image, lex, cfg, keys["ANTHROPIC_API_KEY"])
        op = reading["operation"]["name"]
        prompt = build_reverse_prompt(op, lex[op], reading)
        print(f"op={op}\nprompt={prompt}\n")
        editor = KleinEditor(keys["BFL_API_KEY"], cfg["image"]["max_edge"], cfg["image"]["output_format"])
        cands = []
        for k in range(cfg["run"]["candidates"]):
            seed = cfg["run"]["base_seed"] + k
            path = out_dir / f"cand_{k}.png"
            meta = editor.edit(Path(args.image), prompt, seed, path)
            print(f"candidate {k}: {path}")
            cands.append({"file": path.name, **meta})
        (out_dir / "record.json").write_text(json.dumps(
            {"reading": reading, "operation": op, "prompt": prompt, "candidates": cands}, indent=2))
        print(f"saved to {out_dir}")


main()
