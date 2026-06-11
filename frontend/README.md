# MindSafe Frontend

Flask web app serving the MindSafe landing page and evaluation history dashboard.

---

## What it does

- Landing page explaining MindSafe and linking to the Chrome extension
- `/history` — reads past evaluations from Supabase and displays them in a table
- Proxies evaluation requests to the AI API (optional — mostly for demo purposes outside the extension)

---

## Run locally

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Needs SUPABASE_URL + SUPABASE_KEY and MINDSAFE_API_URL in environment
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_KEY=eyJ...
export MINDSAFE_API_URL=http://localhost:5001

python app.py   # serves on :5000
```

Or via the root `run.sh` which starts both the API and frontend together.

---

## Docker

```bash
# From repo root
docker-compose up frontend
```

Expects `MINDSAFE_API_URL`, `SUPABASE_URL`, `SUPABASE_KEY` as environment variables (set in `ai-agents/.env` or docker-compose env block).

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `MINDSAFE_API_URL` | Yes | URL of the AI API, e.g. `http://api:5001` in Docker or `http://localhost:5001` locally |
| `SUPABASE_URL` | No | Supabase project URL — enables history page |
| `SUPABASE_KEY` | No | Supabase anon key — read-only history display |

---

## Files

```
frontend/
├── app.py              Flask app
├── requirements.txt
├── Dockerfile
├── templates/          Jinja2 HTML templates
└── static/             CSS + JS assets
```
