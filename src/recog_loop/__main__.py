import argparse
from pathlib import Path

from .config import load_config, load_env, load_lexicon


def main():
    p = argparse.ArgumentParser(prog="recog_loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the loop")
    r.add_argument("--image", required=True)
    r.add_argument("--steps", type=int)
    s = sub.add_parser("serve", help="UI on localhost")
    s.add_argument("--port", type=int, default=5000)
    args = p.parse_args()

    if args.cmd == "run":
        from .loop import run
        cfg = load_config()
        print(run(Path(args.image), args.steps or cfg["run"]["steps"], cfg, load_lexicon(), load_env()))
    else:
        from .serve import main as serve
        serve(args.port)


main()
