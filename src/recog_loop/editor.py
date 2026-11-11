"""Reverse-prompt template and the FLUX 3 Klein (Black Forest Labs) client."""
import base64
import io
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps

BFL_URL = "https://api.bfl.ai/v1/flux-3-image-klein"
TERMINAL_FAIL = {"Error", "Failed", "Request Moderated", "Content Moderated", "Task not found", "No Card Generated"}

STRENGTH = {  # Klein has no strength setting; prompt wording is the only lever
    "subtle": "Make a small but visible change.",
    "medium": "The change must be clearly visible.",
    "strong": ("Make a dramatic change: remove it entirely with no trace left, and show the object as it looked "
               "long before this happened. Do not keep a faded or partial version."),
}


def build_reverse_prompt(op_name: str, op_spec: dict, reading: dict, strength: str = "medium") -> str:
    """Template prompt: show the sample before the operation."""
    alter = "; ".join(reading["operation"]["alter"])
    preserve = "; ".join(reading["operation"]["preserve"])
    return (
        f"Edit this photo to show the same object before {op_name.lower().replace('_', ' ')} happened to it. "
        f"Completely remove: {alter}. {op_spec['undo_prompt'].capitalize()}. "
        f"Show the clean material that was underneath, not a faded or blurred version. {STRENGTH[strength]} "
        f"Keep the object's shape and layout: {preserve}. Same framing and camera angle. Photographic macro, not a drawing."
    )


class KleinEditor:
    def __init__(self, api_key: str, max_edge: int = 1024, output_format: str = "png",
                 poll_interval: float = 1.0, timeout: float = 300):
        self.headers = {"x-key": api_key, "Content-Type": "application/json", "accept": "application/json"}
        self.max_edge, self.fmt = max_edge, output_format
        self.poll_interval, self.timeout = poll_interval, timeout

    def _encode(self, path: Path) -> str:
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # honour EXIF rotation
        img.thumbnail((self.max_edge, self.max_edge))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()

    def edit(self, image_path, prompt, seed, out_path):
        body = {"prompt": prompt, "images": [self._encode(image_path)], "seed": seed,
                "output_format": self.fmt}
        r = requests.post(BFL_URL, json=body, headers=self.headers, timeout=60)
        if not r.ok:
            raise RuntimeError(f"BFL submit failed {r.status_code}: {r.text[:500]}")
        sub = r.json()
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            p = requests.get(sub["polling_url"], headers=self.headers, timeout=60)
            p.raise_for_status()
            res = p.json()
            status = res.get("status")
            if status == "Ready":
                # image URLs expire after ~10 min and have no CORS: download immediately
                img = requests.get(res["result"]["sample"], timeout=120)
                img.raise_for_status()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(img.content)
                return {"seed": seed, "prompt": prompt, "bfl_id": sub["id"], "cost": sub.get("cost"),
                        "output_mp": sub.get("output_mp")}
            if status in TERMINAL_FAIL:
                raise RuntimeError(f"BFL task {sub['id']} ended with status {status}: {res}")
        raise TimeoutError(f"BFL task {sub['id']} did not finish in {self.timeout}s")
