"""Load config.yaml, lexicon.yaml and secrets from .env."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_KEYS = {
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/",
    "BFL_API_KEY": "https://dashboard.bfl.ai/",
}


def load_env(required=tuple(REQUIRED_KEYS)) -> dict:
    """Read .env and return the requested keys; exit with a clear message if any are missing."""
    load_dotenv(ROOT / ".env")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        lines = [f"  {k}  (get one at {REQUIRED_KEYS[k]})" for k in missing]
        raise SystemExit(
            "Missing environment variables:\n" + "\n".join(lines)
            + "\nCopy .env.example to .env and fill them in."
        )
    return {k: os.environ[k] for k in required}


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def load_lexicon() -> dict:
    """Return {OP_NAME: {group, family, undo_prompt, visible_signature}}."""
    raw = yaml.safe_load((ROOT / "lexicon.yaml").read_text())
    ops = {}
    for group, entries in raw["groups"].items():
        for name, spec in entries.items():
            ops[name] = {"group": group, **spec}
    return ops
