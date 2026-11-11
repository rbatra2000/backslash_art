"""Blind reflection. Every call here is a fresh, stateless Claude call with the same fixed system prompt.

The judge sees ONLY its own inputs (two images + the operation definition). It never sees the
generation prompt, earlier steps, other candidates, candidate index, or the pipeline's reasoning,
so every judgement starts from the same point.
"""
import base64
import io
from pathlib import Path

import anthropic
from PIL import Image, ImageOps

JUDGE_SYSTEM = """You are an independent, blind observer of image transformations for an art-research experiment.
You are shown Image A (a reference) and Image B (generated from A). B is supposed to show how the sample in A looked
BEFORE a named material process acted on it, i.e. the process has been undone. You know nothing else.
Describe only what you can see, concretely and briefly. Report:
- undone: "yes" if the named process was visibly undone in B, otherwise "no"; reasoning of at most 10 words.
- changes: up to 2 phrases (max 8 words each) naming the most visible differences between A and B (empty if none).
- kept: up to 2 phrases (max 6 words each) naming structure from A that survives in B.
- lost: up to 2 phrases (max 6 words each) naming structure from A that is gone or distorted in B (empty if none).
Be terse. Do not give numeric scores."""

_LIST = {"type": "array", "maxItems": 2, "items": {"type": "string"}}
JUDGE_TOOL = {"name": "judge", "description": "Report observations.", "input_schema": {
    "type": "object", "required": ["undone", "changes", "kept", "lost"],
    "properties": {
        "undone": {"type": "object", "required": ["verdict", "reasoning"], "properties": {
            "verdict": {"type": "string", "enum": ["yes", "no"]},
            "reasoning": {"type": "string"}}},
        "changes": _LIST, "kept": _LIST, "lost": _LIST}}}


def _validate_judge(o):
    if o["undone"]["verdict"] not in ("yes", "no") or not isinstance(o["undone"]["reasoning"], str):
        raise ValueError("undone needs verdict yes|no and string reasoning")
    for k in ("changes", "kept", "lost"):
        if not (isinstance(o[k], list) and all(isinstance(x, str) for x in o[k])):
            raise ValueError(f"{k} must be a list of strings")


def judge(a_path, b_path, op_name, op_spec, api_key, model, max_edge=768) -> dict:
    """Blind comparison of reference A and generated B for one operation."""
    content = [
        {"type": "text", "text": "Image A (reference):"}, _img_block(a_path, max_edge),
        {"type": "text", "text": "Image B (generated):"}, _img_block(b_path, max_edge),
        {"type": "text", "text": (
            f"Process that should have been undone: {op_name.replace('_', ' ')}.\n"
            f"What undoing it means: {op_spec['undo_prompt']}.\n"
            f"What to look for: {op_spec['visible_signature']}.")},
    ]
    return _call_tool(api_key, model, JUDGE_SYSTEM, JUDGE_TOOL, content, _validate_judge)


def _img_block(path: Path, max_edge: int) -> dict:
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    img.thumbnail((max_edge, max_edge))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}}


def _call_tool(api_key, model, system, tool, content, validate, retries=3):
    """Stateless tool call with validation + retry (forced tool_choice is rejected by this model)."""
    client = anthropic.Anthropic(api_key=api_key)
    err = None
    for _ in range(retries):
        text = "Respond by calling the `%s` tool exactly once." % tool["name"]
        if err:
            text += f" Your previous call was invalid: {err}. Fix it."
        resp = client.messages.create(model=model, max_tokens=1500, system=system, tools=[tool],
                                      messages=[{"role": "user", "content": content + [{"type": "text", "text": text}]}])
        out = next((b.input for b in resp.content if b.type == "tool_use"), None)
        try:
            if out is None:
                raise ValueError("no tool call was made")
            validate(out)
            return out
        except (ValueError, TypeError, KeyError) as e:
            err = str(e)
    raise RuntimeError(f"{tool['name']} invalid after {retries} tries: {err}")
