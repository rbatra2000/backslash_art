# before_recognition

A recursive loop that moves **backwards in time** through a material sample's imagined history.

1. A vision model (Claude) reads an image: top-3 possible identities with probabilities.
2. It infers the process that formed the current state and picks an operation from `lexicon.yaml` (e.g. DEPOSIT).
3. We **undo** that operation: FLUX 3 Klein generates how the sample would have looked *before* it.
4. The result is re-read, and the loop repeats (default 10 steps, 3 candidates per step, best one continues).

Ambiguity is tracked as a distribution: each step's readings are stored so you can see how the model's confidence moves as the sample is unmade.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # then fill in ANTHROPIC_API_KEY and BFL_API_KEY
```

Keys live only in `.env` (git-ignored). The code reads them via `src/recog_loop/config.py` and fails with a clear message if one is missing.

## Run

```bash
python -m recog_loop run --image assets/IMG_3572.JPG --steps 3
python -m recog_loop serve        # live + replay UI at http://localhost:5000
```

Outputs go to `runs/<run_id>/` (git-ignored): per-step images, `record.json` with every decision and its reasoning, `events.jsonl` for the UI, and `run.json` with config, seeds, model IDs and the git commit used.

## Files

| File | Purpose |
|---|---|
| `config.yaml` | Steps, candidates, models, selection gates, score weights |
| `lexicon.yaml` | Operations in three groups, each with an `undo_prompt` and `visible_signature` |
| `src/recog_loop/` | Reader, editor, scoring, loop, UI server |

## Reproducibility

Pinned config + lexicon are committed; each run records the commit hash, model IDs, prompts and per-candidate seeds. Hosted models can change over time and the BFL API upsamples prompts, so reruns are close, not guaranteed identical. Every candidate image is archived.

## Git convention

One commit per logical change. The message says what changed and why (the research reasoning), so `git log` doubles as the experiment notebook. Threshold, lexicon and prompt changes get their own commits.

_Status: scaffold. Reader, editor, scoring and UI are added in later commits._
