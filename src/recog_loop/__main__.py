import argparse
import json

from .config import load_config, load_env, load_lexicon


def main():
    p = argparse.ArgumentParser(prog="recog_loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="run the reader once on an image and print the result")
    r.add_argument("--image", required=True)
    args = p.parse_args()

    if args.cmd == "read":
        from .reader import read_image
        keys = load_env(required=["ANTHROPIC_API_KEY"])
        out = read_image(args.image, load_lexicon(), load_config(), keys["ANTHROPIC_API_KEY"])
        print(json.dumps(out, indent=2))


main()
