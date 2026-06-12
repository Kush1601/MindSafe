"""
MindSafe FastAPI — async job-based evaluation API

Endpoints:
  GET  /health                     — liveness check
  POST /evaluate                   — submit job, returns job_id immediately
  GET  /evaluate/{job_id}          — poll job status / result
  GET  /evaluate/{job_id}/fhir     — FHIR R4 Bundle for a completed job

The pipeline (download → Whisper → heuristics → LLM) takes 20-60 s.
Running it synchronously would cause HTTP timeouts. Instead:
  1. POST /evaluate enqueues the work as a BackgroundTask and returns 202.
  2. Client polls GET /evaluate/{job_id} until status == "done" or "failed".
"""

import os
import re
import shutil
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

# Supabase is optional
try:
    from supabase import create_client  # type: ignore
except ImportError:
    create_client = None

load_dotenv()

# ---------- OpenTelemetry ----------
from evaluation.telemetry import init_tracing
_tracer = init_tracing()

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _otel_fastapi_available = True
except ImportError:
    _otel_fastapi_available = False

# ---------- Logging ----------
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
log = structlog.get_logger("mindsafe.api")

# ---------- Config ----------
API_KEY      = os.getenv("MINDSAFE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client is not None:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("supabase.ready")
    except Exception as exc:
        log.warning("supabase.init_failed", error=str(exc))

# ---------- In-memory job store ----------
# Sufficient for a portfolio demo; swap for Redis in prod.
_jobs: dict[str, dict[str, Any]] = {}

# Thread pool for CPU/IO-bound pipeline work (Whisper, OpenCV)
_executor = ThreadPoolExecutor(max_workers=2)

# ---------- App ----------
app = FastAPI(
    title="MindSafe API",
    description="Pediatric media evaluation — async job-based API",
    version="2.0.0",
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

if _otel_fastapi_available:
    FastAPIInstrumentor.instrument_app(app)


# ---------- Auth ----------
def _check_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


# ---------- Request / Response models ----------
class EvaluateRequest(BaseModel):
    url: str = Field(..., description="YouTube video URL")
    age: float = Field(..., ge=0, le=18, description="Child age in years")

    @field_validator("url")
    @classmethod
    def url_must_be_youtube(cls, v: str) -> str:
        if not re.match(
            r"^https?://(www\.)?(youtube\.com/watch\?|youtu\.be/|youtube\.com/shorts/)", v
        ):
            raise ValueError(
                "Only YouTube URLs accepted (youtube.com/watch, youtu.be, youtube.com/shorts)"
            )
        return v.strip()


class TranscriptSegmentIn(BaseModel):
    start: float = Field(0.0, ge=0)
    end: float = Field(0.0, ge=0)
    text: str


class EvaluateTranscriptRequest(BaseModel):
    segments: list[TranscriptSegmentIn] = Field(..., min_length=1)
    age: float = Field(..., ge=0, le=18)
    url: str | None = Field(None, description="Source URL (for caching/logging only)")
    title: str | None = None


class EvaluateMetadataRequest(BaseModel):
    title: str = Field(..., min_length=1)
    age: float = Field(..., ge=0, le=18)
    channel: str | None = None
    url: str | None = None


class JobStatus(BaseModel):
    job_id: str
    status: str            # "queued" | "processing" | "done" | "failed"
    submitted_at: str
    completed_at: str | None = None
    result: dict | None = None
    error: str | None = None


# ---------- Pipeline helpers (unchanged logic from Flask api.py) ----------

def _validate_youtube_url(url: str) -> bool:
    return bool(re.match(
        r"^https?://(www\.)?(youtube\.com/watch\?|youtu\.be/|youtube\.com/shorts/)",
        url,
    ))


from evaluation.utils import canonical_youtube_url as _canonical_url


def _get_cached(video_url: str) -> dict | None:
    if supabase is None:
        return None
    video_url = _canonical_url(video_url)
    try:
        resp = (
            supabase.table("video_eval")
            .select("*")
            .eq("video_path", video_url)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        row = resp.data[0]
        return {k: row.get(k) for k in (
            "video_path", "child_age", "age_band", "age_band_name",
            "duration_seconds", "duration_minutes", "dev_score",
            "dev_interpretation", "brainrot_index", "brainrot_interpretation",
            "overall_recommendation", "dimension_scores", "metrics",
            "strengths", "concerns", "recommendations",
        )}
    except Exception as exc:
        log.warning("cache.lookup_failed", error=str(exc))
        return None


def _save_to_supabase(video_url: str, child_age: float, results: dict) -> None:
    if supabase is None:
        return
    video_url = _canonical_url(video_url)
    try:
        metadata = results.get("metadata", {}) or {}
        overall  = results.get("overall_scores", {}) or {}
        interp   = results.get("interpretations", {}) or {}
        recs     = results.get("recommendations", {}) or {}
        payload = {
            "video_path": video_url,
            "child_age": metadata.get("child_age", child_age),
            "age_band": metadata.get("age_band"),
            "age_band_name": metadata.get("age_band_label"),
            "duration_seconds": metadata.get("duration_seconds"),
            "duration_minutes": metadata.get("duration_minutes"),
            "dev_score": overall.get("development_score"),
            "dev_interpretation": interp.get("developmental"),
            "brainrot_index": overall.get("brainrot_index"),
            "brainrot_interpretation": interp.get("brainrot"),
            "overall_recommendation": interp.get("overall"),
            "dimension_scores": results.get("dimension_scores"),
            "metrics": results.get("raw_metrics"),
            "strengths": recs.get("strengths"),
            "concerns": recs.get("concerns"),
            "recommendations": [interp.get("overall")] if interp.get("overall") else [],
        }
        supabase.table("video_eval").upsert(payload, on_conflict="video_path").execute()
        log.info("cache.saved", url_hash=video_url[:20])
    except Exception as exc:
        log.warning("cache.save_failed", error=str(exc))


def _run_pipeline(job_id: str, youtube_url: str, child_age: float) -> None:
    """
    Blocking pipeline — runs in ThreadPoolExecutor so it doesn't block the
    event loop. Updates _jobs[job_id] when done or failed.
    """
    from evaluation.deid import pseudonymize_url
    from evaluation.evaluate_video import evaluate_video

    _jobs[job_id]["status"] = "processing"
    log.info("job.start", job_id=job_id, video_id=pseudonymize_url(youtube_url), age=child_age)

    temp_dir = Path(tempfile.mkdtemp(prefix="ms_eval_"))
    try:
        # Step 1 — download + extract
        from video_data_extraction.main import process_youtube_video
        process_youtube_video(
            youtube_url, str(temp_dir),
            use_chunked_processing=False,
            segment_duration=30.0,
            frames_per_segment=20,
            audio_chunk_duration=60.0,
        )

        # Step 2 — evaluate
        video_path = temp_dir / "video_with_audio.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"Extracted video not found: {video_path}")

        llm_client = None
        if ANTHROPIC_KEY:
            from evaluation.llm_client import LLMClient
            llm_client = LLMClient(api_key=ANTHROPIC_KEY)

        results = evaluate_video(
            video_path=str(video_path),
            child_age=child_age,
            llm_client=llm_client,
            outputs_dir=str(temp_dir),
            compute_motion=False,
        )

        # Step 3 — parent summary
        if llm_client is not None:
            try:
                results["parent_summary"] = llm_client.generate_parent_summary(
                    {
                        "overall_scores": results.get("overall_scores"),
                        "interpretations": results.get("interpretations"),
                        "dimension_scores": results.get("dimension_scores"),
                        "recommendations": results.get("recommendations"),
                    },
                    child_age,
                )
            except Exception as exc:
                log.warning("parent_summary.failed", job_id=job_id, error=str(exc))

        # Step 4 — cache
        _save_to_supabase(youtube_url, child_age, results)

        overall = results.get("overall_scores", {})
        log.info(
            "job.done", job_id=job_id,
            dev_score=overall.get("development_score"),
            brainrot_index=overall.get("brainrot_index"),
        )
        _jobs[job_id].update(
            status="done",
            completed_at=datetime.now(UTC).isoformat(),
            result=results,
        )

    except Exception as exc:
        log.error("job.failed", job_id=job_id, error=str(exc))
        _jobs[job_id].update(
            status="failed",
            completed_at=datetime.now(UTC).isoformat(),
            error=str(exc),
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _run_transcript_pipeline(job_id: str, segments: list, child_age: float,
                             url: str | None, title: str | None) -> None:
    """Evaluate using client-supplied transcript text — no YouTube download."""
    from evaluation.evaluate_video import evaluate_transcript
    from evaluation.video_preprocess import TranscriptSegment

    _jobs[job_id]["status"] = "processing"
    log.info("job.start", job_id=job_id, mode="transcript", age=child_age)

    try:
        ts = [TranscriptSegment(start=s.start, end=s.end, text=s.text) for s in segments]

        llm_client = None
        if ANTHROPIC_KEY:
            from evaluation.llm_client import LLMClient
            llm_client = LLMClient(api_key=ANTHROPIC_KEY)

        results = evaluate_transcript(ts, child_age, llm_client=llm_client, video_title=title)

        if llm_client is not None:
            try:
                results["parent_summary"] = llm_client.generate_parent_summary(
                    {
                        "overall_scores": results.get("overall_scores"),
                        "interpretations": results.get("interpretations"),
                        "dimension_scores": results.get("dimension_scores"),
                        "recommendations": results.get("recommendations"),
                    },
                    child_age,
                )
            except Exception as exc:
                log.warning("parent_summary.failed", job_id=job_id, error=str(exc))

        if url:
            _save_to_supabase(url, child_age, results)

        log.info("job.done", job_id=job_id, mode="transcript")
        _jobs[job_id].update(
            status="done",
            completed_at=datetime.now(UTC).isoformat(),
            result=results,
        )
    except Exception as exc:
        log.error("job.failed", job_id=job_id, error=str(exc))
        _jobs[job_id].update(
            status="failed",
            completed_at=datetime.now(UTC).isoformat(),
            error=str(exc),
        )


def _run_metadata_pipeline(job_id: str, title: str, child_age: float,
                           channel: str | None, url: str | None) -> None:
    """Title/channel-only estimate when a video has no captions."""
    from evaluation.evaluate_video import evaluate_metadata

    _jobs[job_id]["status"] = "processing"
    log.info("job.start", job_id=job_id, mode="metadata", age=child_age)

    try:
        llm_client = None
        if ANTHROPIC_KEY:
            from evaluation.llm_client import LLMClient
            llm_client = LLMClient(api_key=ANTHROPIC_KEY)

        results = evaluate_metadata(title, child_age, channel=channel, llm_client=llm_client)

        if url:
            _save_to_supabase(url, child_age, results)

        log.info("job.done", job_id=job_id, mode="metadata")
        _jobs[job_id].update(
            status="done",
            completed_at=datetime.now(UTC).isoformat(),
            result=results,
        )
    except Exception as exc:
        log.error("job.failed", job_id=job_id, error=str(exc))
        _jobs[job_id].update(
            status="failed",
            completed_at=datetime.now(UTC).isoformat(),
            error=str(exc),
        )


# ---------- Routes ----------

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "MindSafe API",
        "version": "2.0.0",
        "supabase": supabase is not None,
        "llm": ANTHROPIC_KEY is not None,
    }


@app.post("/evaluate", status_code=202, dependencies=[Depends(_check_api_key)])
def submit_evaluation(body: EvaluateRequest):
    """
    Submit a video for evaluation. Returns a job_id immediately (HTTP 202).
    Poll GET /evaluate/{job_id} for results.
    """
    from evaluation.deid import pseudonymize_url

    # Cache hit → wrap in a completed job and return immediately
    cached = _get_cached(body.url)
    if cached is not None:
        job_id = str(uuid.uuid4())[:8]
        now = datetime.now(UTC).isoformat()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "done",
            "submitted_at": now,
            "completed_at": now,
            "result": cached,
            "error": None,
        }
        log.info("evaluate.cache_hit", job_id=job_id, video_id=pseudonymize_url(body.url))
        return {"job_id": job_id, "status": "done", "cache_hit": True}

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "submitted_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "result": None,
        "error": None,
    }

    # Run pipeline in thread pool (Whisper/OpenCV are not async-friendly)
    _executor.submit(_run_pipeline, job_id, body.url, body.age)

    log.info(
        "evaluate.queued", job_id=job_id,
        video_id=pseudonymize_url(body.url), age=body.age,
    )
    return {"job_id": job_id, "status": "queued"}


@app.post("/evaluate/transcript", status_code=202, dependencies=[Depends(_check_api_key)])
def submit_transcript_evaluation(body: EvaluateTranscriptRequest):
    """
    Evaluate a video from its transcript (captions fetched client-side).
    Returns a job_id immediately (HTTP 202). Poll GET /evaluate/{job_id}.

    This path avoids server-side YouTube download — the extension fetches
    captions from the user's own browser session, sidestepping bot detection.
    """
    # Cache hit on URL → return immediately
    if body.url:
        cached = _get_cached(body.url)
        if cached is not None:
            job_id = str(uuid.uuid4())[:8]
            now = datetime.now(UTC).isoformat()
            _jobs[job_id] = {
                "job_id": job_id, "status": "done",
                "submitted_at": now, "completed_at": now,
                "result": cached, "error": None,
            }
            log.info("evaluate.cache_hit", job_id=job_id, mode="transcript")
            return {"job_id": job_id, "status": "done", "cache_hit": True}

    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id, "status": "queued",
        "submitted_at": datetime.now(UTC).isoformat(),
        "completed_at": None, "result": None, "error": None,
    }
    _executor.submit(
        _run_transcript_pipeline, job_id, body.segments, body.age, body.url, body.title
    )
    log.info("evaluate.queued", job_id=job_id, mode="transcript",
             segments=len(body.segments), age=body.age)
    return {"job_id": job_id, "status": "queued"}


@app.post("/evaluate/metadata", status_code=202, dependencies=[Depends(_check_api_key)])
def submit_metadata_evaluation(body: EvaluateMetadataRequest):
    """
    Estimate suitability from title/channel alone — used when a video has no
    captions, so neither transcript nor server-side download is possible.
    Lower confidence; result is flagged analysis_mode == "metadata_only".
    """
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {
        "job_id": job_id, "status": "queued",
        "submitted_at": datetime.now(UTC).isoformat(),
        "completed_at": None, "result": None, "error": None,
    }
    _executor.submit(
        _run_metadata_pipeline, job_id, body.title, body.age, body.channel, body.url
    )
    log.info("evaluate.queued", job_id=job_id, mode="metadata", age=body.age)
    return {"job_id": job_id, "status": "queued"}


@app.get("/evaluate/{job_id}", dependencies=[Depends(_check_api_key)])
def get_job(job_id: str):
    """Poll evaluation job status. Returns result when status == 'done'."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@app.get("/evaluate/{job_id}/fhir", dependencies=[Depends(_check_api_key)])
def get_job_fhir(job_id: str):
    """Return FHIR R4 Bundle for a completed evaluation job."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail=f"Job not complete (status: {job['status']})")

    try:
        from evaluation.fhir_export import evaluation_to_fhir_bundle
        bundle = evaluation_to_fhir_bundle(job["result"], child_age=job["result"].get("metadata", {}).get("child_age", 0))
        return Response(
            content=bundle.model_dump_json(indent=2),
            media_type="application/fhir+json",
        )
    except Exception as exc:
        log.error("fhir.export_failed", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"FHIR export failed: {exc}")


# ---------- Error handlers ----------

@app.exception_handler(404)
async def not_found(_req: Request, _exc):
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.exception_handler(500)
async def server_error(_req: Request, exc):
    log.error("unhandled_exception", error=str(exc))
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# ---------- Dev runner ----------

if __name__ == "__main__":
    import uvicorn
    print("MindSafe API v2 — http://127.0.0.1:5001")
    print("Docs: http://127.0.0.1:5001/docs")
    uvicorn.run("api:app", host="127.0.0.1", port=5001, reload=True)
