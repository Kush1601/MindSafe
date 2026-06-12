# MindSafe

A clinical-AI pipeline that evaluates YouTube and YouTube Kids videos for developmental appropriateness, delivering a 1–10 safety score directly inside the browser.

---

## What it does

- Reads a YouTube video's **transcript** and a child's age
- Computes heuristic + optional LLM metrics across 6 developmental dimensions
- Returns a **Developmental Score (0–100)**, **Brainrot Index (0–100)**, and **1–10 MindSafe rating**
- Displays the score as a card injected directly into YouTube via a Chrome extension
- Exports results as **FHIR R4 Bundles** (Observations with LOINC codes, RiskAssessment, DocumentReference)
- Caches evaluations in **Supabase** so repeat lookups are instant

### How the transcript is obtained (3-tier, browser-side)

YouTube blocks server-side video downloads from datacenter IPs, so the
Chrome extension obtains the transcript from the user's own browser session
and sends only **text** to the API — no video or audio leaves the device:

1. **Captions** — if the video has captions, the extension fetches the
   transcript directly (instant, full analysis).
2. **In-browser Whisper** — if there are no captions, a Whisper model runs
   locally in the browser (WebGPU / WASM via `transformers.js`) to transcribe
   the audio. No server, no upload, works on any device.
3. **Metadata estimate** — if transcription isn't possible, the API produces a
   lower-confidence estimate from the title/channel, clearly flagged as such.

---

## Architecture

```
chrome_extension/        Chrome MV3 extension — injects score card into YouTube
frontend/                Flask web app — landing page + evaluation history dashboard
ai-agents/               FastAPI backend — video pipeline, scoring, FHIR export
infra/                   ECS task definitions, deploy scripts, docker-compose
```

### Pipeline stages (each traced with OpenTelemetry)

```
transcript (from captions, in-browser Whisper, or metadata fallback)
  → text metrics (vocabulary, utterance length, question rate)
  → LLM semantic pass (Claude, optional — gated by ANTHROPIC_API_KEY)
  → narrative coherence
  → heuristic metrics (language, SEL, narrative, fantasy, interactivity)
  → guardrails (validate → repair-retry → safety floor → abstention)
  → score (age-band normalized)
  → cache (Supabase upsert)
  → FHIR R4 export (on request)
```

A full local pipeline (`download → ffmpeg → local Whisper → visual/audio
pacing`) also exists in `ai-agents/` for running the complete multimodal
analysis offline, where YouTube's bot-detection does not apply.

### Guardrails

4-layer LLM safety system modeled on FDA AI/ML-SaMD guidance:
1. Schema validation
2. Repair-retry (up to 2 attempts)
3. Safety floor (hard limits on aggression/fear thresholds)
4. Abstention (returns null score rather than unsafe output)

---

## Quickstart (local)

Requirements: Python 3.10–3.11, `ffmpeg` (`brew install ffmpeg python@3.11`).

```bash
# Set up and run everything
python3.11 -m venv ai-agents/venv
ai-agents/venv/bin/pip install -r ai-agents/requirements.txt
python3.11 -m venv frontend/venv
frontend/venv/bin/pip install -r frontend/requirements.txt

cp ai-agents/.env.example ai-agents/.env  # add ANTHROPIC_API_KEY + Supabase keys

./run.sh   # API on :5001  •  frontend on :5000
```

Without `ANTHROPIC_API_KEY` the pipeline runs in heuristics-only fast mode.

**Load the extension:**
1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select `chrome_extension/`
3. Open YouTube — the MindSafe card appears on any watch page

---

## Docker (local / EC2)

```bash
# Development (includes Jaeger tracing UI at :16686)
docker-compose up

# Production (no Jaeger, fits EC2 t2.micro)
docker-compose -f docker-compose.prod.yml up -d
```

Environment variables needed (set in `.env` or shell):

```
ANTHROPIC_API_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
```

---

## Deployment

Runs on a single **EC2** instance via `docker-compose -f docker-compose.prod.yml`
(API + frontend + PO-token sidecar). See [infra/README.md](infra/README.md) for
the full step-by-step, including an ECS Fargate option for scaling up.

---

## API

```
POST /evaluate             Submit a URL (server-side download) — { job_id, status }, HTTP 202
POST /evaluate/transcript  Submit transcript segments (browser-side) — { job_id, status }
POST /evaluate/metadata    Title/channel-only estimate (no transcript available)
GET  /evaluate/{id}        Poll job status / result
GET  /evaluate/{id}/fhir   FHIR R4 Bundle for completed job
GET  /health               Liveness check
GET  /docs                 Auto-generated OpenAPI docs
```

The Chrome extension uses `/evaluate/transcript` (and `/evaluate/metadata` as a
fallback); `/evaluate` is the server-side path for offline/local use.

Full API docs: [ai-agents/README.md](ai-agents/README.md)

---

## Scores

| Score | Range | Direction |
|---|---|---|
| Developmental Score | 0–100 | Higher is better |
| Brainrot Index | 0–100 | Lower is better |
| MindSafe Rating | 1–10 | Higher is better |

6 dimension scores: **Pacing**, **Story**, **Language**, **SEL**, **Fantasy**, **Interactivity**

Full explanations: [MINDSAFE_SCORES.md](MINDSAFE_SCORES.md)

---

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI + Pydantic v2, async job pattern (ThreadPoolExecutor) |
| Transcription | Whisper (local, no audio sent to cloud) |
| LLM | Claude (Anthropic) — structured output with schema validation |
| Database / Cache | Supabase (PostgreSQL) |
| Observability | OpenTelemetry → Jaeger |
| Logging | structlog (JSON, request-ID correlation) |
| FHIR | R4 Bundles — LOINC-coded Observations, SNOMED RiskAssessment |
| CI | GitHub Actions — lint, pytest, eval regression gate (≥70% F1) |
| Deploy | Docker + AWS ECS Fargate |
| Extension | Chrome MV3, async polling, exponential backoff |

---

## Eval harness

Regression gate in CI prevents deploying a model regression:

```bash
python -m evaluation.evals.run_evals --fail-below 0.70
```

22-video gold set covering: age bands 0–12, edge cases (safety floor triggers, SEL-heavy content, consumerist content, multilingual).

---

## De-identification & HIPAA

- URLs pseudonymized before storage (SHA-256 hash)
- PII scrubbed from logs
- HIPAA data flow documented in `ai-agents/evaluation/deid.py`
- FHIR exports use pseudonymized patient IDs

---

## Project structure

```
MindSafe/
├── ai-agents/              FastAPI backend + evaluation pipeline
│   ├── api.py
│   ├── evaluation/
│   │   ├── evaluate_video.py
│   │   ├── guardrails.py
│   │   ├── fhir_export.py
│   │   ├── telemetry.py
│   │   ├── deid.py
│   │   └── evals/
│   ├── video_data_extraction/
│   ├── tests/
│   └── Dockerfile
├── chrome_extension/       Chrome MV3 extension
│   ├── content_script.js   Caption fetch + score card injection
│   ├── whisper.js          In-browser Whisper transcription (transformers.js)
│   ├── background.js       Service worker — API calls + polling
│   └── vendor/             Bundled transformers.js + ONNX runtime WASM
├── frontend/               Flask landing page + history dashboard
├── infra/                  ECS task definitions + deploy scripts
├── docker-compose.yml      Local dev (with Jaeger)
├── docker-compose.prod.yml Production (EC2 / bare metal)
└── .github/workflows/      CI (lint + pytest + eval gate)
```
