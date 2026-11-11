"""Blind scoring. Every call here is a fresh, stateless Claude call with the same fixed system prompt.

The judge sees ONLY its own inputs (two images + the operation definition). It never sees the
generation prompt, earlier steps, other candidates, candidate index, or the pipeline's reasoning,
so every judgement starts from the same point.
"""
import base64
import io
import math
from pathlib import Path

import anthropic
from PIL import Image, ImageOps

JUDGE_SYSTEM = """You are an independent, blind evaluator of image transformations for an art-research experiment.
You are shown Image A (a reference) and Image B (a candidate that was generated from A). B is supposed to show
how the sample in A looked BEFORE a named material process acted on it, i.e. the process has been undone.
You know nothing else. Judge only what you can see. Score each on 0.0-1.0:
- legibility: was the named process visibly undone in B? 0 = no visible undo (or the opposite happened), 1 = clearly undone.
- inheritance: does something structurally specific from A survive in B (form, boundaries, geometry, distinctive features)?
  0 = unrelated image, 1 = same object and structure. Judge structure, not colour.
- change: how visibly different is B from A overall? 0 = identical or nearly so, 0.3 = subtle, 0.6 = clearly different, 1 = dramatically different.
Give one short sentence of reasoning for each. Be calibrated; use the whole range."""

ALIGN_SYSTEM = """You group free-text image-reading labels into shared semantic categories so that probability
distributions from different readings can be compared. Labels that name essentially the same kind of thing
(e.g. 'salt crust on ceramic' and 'mineral efflorescence') get the same short category name (1-3 words).
Different kinds of thing get different categories. Use only the labels given; do not invent new ones."""


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


_SCORE = {"type": "object", "required": ["score", "reasoning"],
          "properties": {"score": {"type": "number"}, "reasoning": {"type": "string"}}}
JUDGE_TOOL = {"name": "judge", "description": "Report scores.", "input_schema": {
    "type": "object", "required": ["legibility", "inheritance", "change"],
    "properties": {"legibility": _SCORE, "inheritance": _SCORE, "change": _SCORE}}}


def _validate_judge(o):
    for k in ("legibility", "inheritance", "change"):
        s = o[k]["score"]
        if not (isinstance(s, (int, float)) and 0 <= s <= 1) or not isinstance(o[k]["reasoning"], str):
            raise ValueError(f"{k} needs score in [0,1] and string reasoning")


def judge(a_path, b_path, op_name, op_spec, api_key, model, max_edge=768) -> dict:
    """Blind comparison of reference A and candidate B for one operation."""
    content = [
        {"type": "text", "text": "Image A (reference):"}, _img_block(a_path, max_edge),
        {"type": "text", "text": "Image B (candidate):"}, _img_block(b_path, max_edge),
        {"type": "text", "text": (
            f"Process that should have been undone: {op_name.replace('_', ' ')}.\n"
            f"What undoing it means: {op_spec['undo_prompt']}.\n"
            f"What to look for: {op_spec['visible_signature']}.")},
    ]
    return _call_tool(api_key, model, JUDGE_SYSTEM, JUDGE_TOOL, content, _validate_judge)


ALIGN_TOOL = {"name": "align", "description": "Assign each label a category.", "input_schema": {
    "type": "object", "required": ["assignments"], "properties": {"assignments": {
        "type": "array", "items": {"type": "object", "required": ["label", "category"],
                                   "properties": {"label": {"type": "string"}, "category": {"type": "string"}}}}}}}


def align_categories(label_sets: dict[str, list[str]], api_key, model) -> dict[str, str]:
    """Map every distinct label (across all readings) to a shared category. Returns {label: category}."""
    labels = sorted({l for ls in label_sets.values() for l in ls})

    def validate(o):
        got = {a["label"] for a in o["assignments"]}
        if got != set(labels):
            raise ValueError(f"assignments must cover exactly these labels, missing/extra: {set(labels) ^ got}")

    text = "Labels:\n" + "\n".join(f"- {l}" for l in labels)
    out = _call_tool(api_key, model, ALIGN_SYSTEM, ALIGN_TOOL, [{"type": "text", "text": text}], validate)
    return {a["label"]: a["category"] for a in out["assignments"]}


def to_distribution(reading: dict, cat_of: dict[str, str]) -> dict[str, float]:
    d: dict[str, float] = {}
    for r in reading["readings"]:
        c = cat_of[r["label"]]
        d[c] = d.get(c, 0.0) + r["probability"]
    return d


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence, base 2, so 0 = identical and 1 = disjoint."""
    keys = set(p) | set(q)
    m = {k: 0.5 * (p.get(k, 0) + q.get(k, 0)) for k in keys}

    def kl(a):
        return sum(a[k] * math.log2(a[k] / m[k]) for k in keys if a.get(k, 0) > 0)

    return 0.5 * kl(p) + 0.5 * kl(q)


def entropy(p: dict[str, float]) -> float:
    return -sum(v * math.log2(v) for v in p.values() if v > 0)
