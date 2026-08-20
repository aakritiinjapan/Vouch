# Vouch — project sources

The full project README, quickstart and architecture notes live at the
**[repository root](../README.md)**.

This directory holds the sources:

| Path | What's in it |
|---|---|
| [`backend/`](backend) | FastAPI + SQLModel service — the guardian, orchestrator, pricing engine and REST API |
| [`frontend/`](frontend) | React + Vite + TypeScript dashboard (the decision queue) |
| [`docs/`](docs) | Scraper Studio notes, demo script, motivation, and the real collector output |

To run everything, use `./demo.sh` from the repository root rather than starting the two halves by
hand. If you do want them separately:

```bash
# backend  (from vouch/backend)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.seed          # seeds from the real collector output
uvicorn app.main:app --reload   # http://127.0.0.1:8000  (/docs for the API)

# frontend  (from vouch/frontend)
npm install && npm run dev      # http://127.0.0.1:5173, proxies /api to the backend

# tests  (from vouch/backend)
pytest -q                       # 181 tests
```

Everything defaults to offline operation — no Bright Data or Anthropic credentials are required.
See [`.env.example`](../.env.example) at the repository root for the variables that enable the live
paths.
