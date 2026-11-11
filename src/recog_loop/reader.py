"""Claude vision reader: image -> readings, formation hypothesis, operation to undo."""
import base64
import io

import anthropic
from PIL import Image

SYSTEM = """You are a materials-aware image reader for an art-research experiment that moves BACKWARDS in time.

Given an image of a material sample you will:
1. READ: give exactly 3 candidate identities for what the image shows, with probabilities summing to 1.
   Candidates may come from different semantic domains (mineral, biological, planetary, built, ...).
   Give the visual evidence for each. Ambiguity is the point: do not collapse to one answer.
2. HYPOTHESIZE one formation process: what material process most plausibly produced the CURRENT state.
3. CHOOSE the single lexicon operation that names that formation process. The loop will then UNDO it,
   generating how the sample looked BEFORE that process acted. So pick the operation that actually
   happened to produce what is visible (e.g. a crust that built up = DEPOSIT), not its inverse.
4. List what must be PRESERVED (structure that existed before the process and should survive the undo:
   major boundaries, host form, base texture) and what to ALTER (the product of the process that the undo removes).
Keep every reasoning field short (1-2 sentences) and grounded in what is visible."""


def encode_image(path, max_edge: int) -> tuple[str, str]:
    """Downscale to max_edge and return (base64, media_type)."""
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"


def _tool_schema(op_names: list[str]) -> dict:
    return {
        "name": "report",
        "description": "Report the reading, formation hypothesis and operation.",
        "input_schema": {
            "type": "object",
            "required": ["readings", "scale_estimate", "formation", "operation"],
            "properties": {
                "readings": {
                    "type": "array", "minItems": 3, "maxItems": 3,
                    "items": {
                        "type": "object",
                        "required": ["label", "probability", "evidence"],
                        "properties": {
                            "label": {"type": "string"},
                            "probability": {"type": "number"},
                            "evidence": {"type": "string"},
                        },
                    },
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


def read_image(path, lexicon: dict, cfg: dict, api_key: str, prior_context: str | None = None) -> dict:
    """One reader call. Each call is stateless; pass prior_context only if you want history-aware reading."""
    data, media = encode_image(path, cfg["image"]["max_edge"])
    client = anthropic.Anthropic(api_key=api_key)
    text = _lexicon_text(lexicon)
    if prior_context:
        text += f"\n\nContext from earlier steps:\n{prior_context}"
    resp = client.messages.create(
        model=cfg["models"]["reader"],
        max_tokens=2000,
        system=SYSTEM,
        tools=[_tool_schema(list(lexicon))],
        # this model rejects forced tool_choice, so instruct instead and verify below
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}},
            {"type": "text", "text": text + "\n\nRespond by calling the `report` tool exactly once."},
        ]}],
    )
    out = next((b.input for b in resp.content if b.type == "tool_use"), None)
    if out is None:
        raise RuntimeError(f"Reader did not call the report tool. Got: {resp.content}")
    total = sum(r["probability"] for r in out["readings"]) or 1.0
    for r in out["readings"]:  # normalise in case the model's probabilities are slightly off
        r["probability"] = round(r["probability"] / total, 4)
    return out
