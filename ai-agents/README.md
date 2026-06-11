# MindSafe AI Evaluation Pipeline

Evaluates YouTube videos for developmental appropriateness. Takes a URL + child age and returns a structured score across 6 dimensions.

## Quick Start

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # add ANTHROPIC_API_KEY (optional) + Supabase keys (optional)

# CLI
python main.py --url "https://youtube.com/watch?v=VIDEO_ID" --age 4

# API server (http://localhost:5001, docs at /docs)
python api.py
```

Without `ANTHROPIC_API_KEY` the pipeline runs in heuristics-only mode. With it, Claude performs semantic analysis.

## Requirements

- Python 3.10–3.11
- FFmpeg (`brew install ffmpeg`)
- Anthropic API key (optional)
- Supabase project (optional — enables result caching)

## Project Structure

```
ai-agents/
├── api.py                      # FastAPI server (async job-based)
├── main.py                     # CLI entry point
├── requirements.txt
├── Dockerfile
├── evaluation/
│   ├── config.py               # Thresholds, age bands, metric definitions
│   ├── evaluate_video.py       # Main evaluator
│   ├── llm_client.py           # Anthropic API wrapper
│   ├── scoring.py              # Score calculation
│   ├── metrics_*.py            # Metric computation modules
│   ├── guardrails.py           # LLM output validation
│   ├── deid.py                 # URL pseudonymization
│   ├── fhir_export.py          # FHIR R4 Bundle export
│   ├── telemetry.py            # OpenTelemetry tracing
│   ├── batch_evaluate.py       # Batch processing CLI
│   └── evals/                  # Eval harness + gold set
├── video_data_extraction/      # Download → Whisper → frame extraction
├── tests/                      # Unit tests (pytest)
├── migrations/                 # Supabase SQL migrations
└── docs/                       # Example FHIR output
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/evaluate` | Submit job (returns `job_id`, HTTP 202) |
| GET | `/evaluate/{job_id}` | Poll job status / result |
| GET | `/evaluate/{job_id}/fhir` | FHIR R4 Bundle for completed job |

## Scores

- **Developmental Score (0–100)** — higher is better
- **Brainrot Index (0–100)** — lower is better
- **6 dimension scores**: Pacing, Story, Language, SEL, Fantasy, Interactivity

See `../MINDSAFE_SCORES.md` for detailed explanations.
