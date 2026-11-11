"""Local UI: follows runs/<id>/events.jsonl (live or replay) and starts runs. Localhost only."""
import json
import re
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from .config import ROOT, load_config, load_env, load_lexicon
from .loop import run

RUNS = ROOT / "runs"
ASSETS = ROOT / "assets"
STATIC = Path(__file__).parent / "static"
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

app = Flask(__name__)


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/runs")
def runs():
    ids = sorted((p.name for p in RUNS.iterdir() if (p / "events.jsonl").exists()), reverse=True) if RUNS.exists() else []
    return jsonify(ids)


@app.get("/api/assets")
def assets():
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    return jsonify(sorted(p.name for p in ASSETS.iterdir() if p.suffix.lower() in exts))


@app.get("/runs/<run_id>/<path:rel>")
def run_file(run_id, rel):
    if not SAFE_ID.match(run_id):
        abort(404)
    return send_from_directory(RUNS / run_id, rel)


@app.get("/stream/<run_id>")
def stream(run_id):
    """SSE: replay everything already in events.jsonl, then follow until run_end."""
    if not SAFE_ID.match(run_id):
        abort(404)
    path = RUNS / run_id / "events.jsonl"
    if not path.exists():
        abort(404)

    def gen():
        pos, idle = 0, 0
        with path.open("r") as f:
            while True:
                f.seek(pos)
                line = f.readline()
                if line and line.endswith("\n"):
                    pos = f.tell()
                    idle = 0
                    yield f"data: {line.strip()}\n\n"
                    if json.loads(line)["type"] == "run_end":
                        return
                else:
                    idle += 1
                    if idle % 15 == 0:
                        yield ": keepalive\n\n"
                    time.sleep(0.4)

    return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/start")
def start():
    body = request.get_json(force=True)
    image = ASSETS / Path(str(body.get("image", ""))).name  # assets/ only
    if not image.exists():
        return jsonify(error="image not found in assets/"), 400
    steps = int(body.get("steps", 3))
    if not 1 <= steps <= 20:
        return jsonify(error="steps must be 1-20"), 400
    run_id = time.strftime("%Y%m%d-%H%M%S")
    cfg, lex, keys = load_config(), load_lexicon(), load_env()
    threading.Thread(target=run, args=(image, steps, cfg, lex, keys, run_id), daemon=True).start()
    for _ in range(50):  # wait for events.jsonl so the page can attach
        if (RUNS / run_id / "events.jsonl").exists():
            break
        time.sleep(0.1)
    return jsonify(run_id=run_id)


def main(port: int = 5000):
    RUNS.mkdir(exist_ok=True)
    print(f"UI at http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
