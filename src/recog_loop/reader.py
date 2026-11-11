"""Claude vision reader: image -> identity, formation hypothesis, operation to undo."""
import base64
import io

import anthropic
from PIL import Image, ImageOps

SYSTEM = """You read images of material samples for an experiment that moves BACKWARDS in time.
1. READ: one guess for what the material is (any domain), with visible evidence.
2. HYPOTHESIZE the process that most likely happened to that material to produce the current surface.
   The object's form (holes, cavities, ridges, shape) is not a process product: never undo it.
   Choose a process that acted on its surface material (coatings, crusts, stains, corrosion, colour).
3. CHOOSE the lexicon operation naming that process (what happened, not its inverse). It will be undone
   to show the sample before.
4. List what to PRESERVE and what to ALTER (undo).
Be terse: label max 8 words, evidence 10, reasoning 12, lists max 3 short items."""


def encode_image(path, max_edge: int) -> tuple[str, str]:
    """Downscale to max_edge and return (base64, media_type)."""
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # honour EXIF rotation
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


def _tool_schema(op_names: list[str]) -> dict:
    return {
        "name": "report",
        "description": "Report the identity, formation hypothesis and operation.",
        "input_schema": {
            "type": "object",
            "required": ["identity", "scale_estimate", "formation", "operation"],
            "properties": {
                "identity": {
                    "type": "object",
                    "required": ["label", "evidence"],
                    "properties": {"label": {"type": "string"}, "evidence": {"type": "string"}},
                },
                "scale_estimate": {"type": "string", "description": "e.g. '2-3 cm field of view'"},
                "formation": {
                    "type": "object",
                    "required": ["process", "evidence", "reasoning"],
                    "properties": {
                        "process": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "reasoning": {"type": "string"},
                    },
                },
                "operation": {
                    "type": "object",
                    "required": ["name", "reasoning", "preserve", "alter"],
                    "properties": {
                        "name": {"type": "string", "enum": op_names},
                        "reasoning": {"type": "string", "description": "why this lexicon op matches the formation process"},
                        "preserve": {"type": "array", "items": {"type": "string"}},
                        "alter": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        },
    }


def _lexicon_text(lexicon: dict) -> str:
    lines = ["Lexicon (forward processes; the loop will undo the one you choose):"]
    for name, s in lexicon.items():
        lines.append(f"- {name} [{s['group']}/{s['family']}]: undo = {s['undo_prompt']}")
    return "\n".join(lines)


def validate(out: dict, op_names: list[str]) -> None:
    """Raise ValueError describing the first schema problem (tool schemas aren't enforced for this model)."""
    if not isinstance(out, dict):
        raise ValueError("report must be an object")
    i = out.get("identity")
    if not (isinstance(i, dict) and isinstance(i.get("label"), str) and isinstance(i.get("evidence"), str)):
        raise ValueError("`identity` must be an object with string label and evidence")
    f = out.get("formation")
    if not (isinstance(f, dict) and {"process", "evidence", "reasoning"} <= f.keys()):
        raise ValueError("`formation` must be an object with process, evidence (list), reasoning")
    o = out.get("operation")
    if not (isinstance(o, dict) and {"name", "reasoning", "preserve", "alter"} <= o.keys()):
        raise ValueError("`operation` must be an object with name, reasoning, preserve (list), alter (list), not a string")
    if o["name"] not in op_names:
        raise ValueError(f"operation.name must be one of {op_names}")
    if not (isinstance(o["preserve"], list) and isinstance(o["alter"], list)):
        raise ValueError("operation.preserve and operation.alter must be lists of strings")


def read_image(path, lexicon: dict, cfg: dict, api_key: str, retries: int = 3) -> dict:
    """One stateless reader call."""
    data, media = encode_image(path, cfg["image"]["max_edge"])
    client = anthropic.Anthropic(api_key=api_key)
    text = _lexicon_text(lexicon)
    last_err = None
    for attempt in range(retries):
        note = f"\n\nYour previous report was invalid: {last_err}. Fix it." if last_err else ""
        resp = client.messages.create(
            model=cfg["models"]["reader"],
            max_tokens=2000,
            system=SYSTEM,
            tools=[_tool_schema(list(lexicon))],
            # this model rejects forced tool_choice, so instruct instead and validate below
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
                {"type": "text", "text": text + "\n\nRespond by calling the `report` tool exactly once." + note},
            ]}],
        )
        out = next((b.input for b in resp.content if b.type == "tool_use"), None)
        try:
            if out is None:
                raise ValueError("no `report` tool call was made")
            validate(out, list(lexicon))
            break
        except ValueError as e:
            last_err = str(e)
    else:
        raise RuntimeError(f"Reader gave an invalid report {retries} times: {last_err}")
    return out
