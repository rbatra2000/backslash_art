# before_recognition

Walks a material sample backwards in time. Claude reads the image and infers what happened to it, FLUX 3 Klein shows it before that, repeat.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add ANTHROPIC_API_KEY and BFL_API_KEY
PYTHONPATH=src python -m recog_loop run --image assets/IMG_3572.JPG
PYTHONPATH=src python -m recog_loop serve   # UI: http://127.0.0.1:5000
```

- `config.yaml`: steps, seed, models, strength. `lexicon.yaml`: operations.
- Output: `runs/<timestamp>/` (git-ignored): `step_NN/{input,result}.png`, `record.json`, `final.json`, `events.jsonl`, `run.json`.
- No scoring, retries or selection. One image per step; the chain is the record.
- Idea: [docs/idea.md](docs/idea.md). Diagrams: [docs/architecture.md](docs/architecture.md).
- Commits explain why each change was made.
