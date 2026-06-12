import os
from pathlib import Path
from io import BytesIO
import zipfile

from flask import Flask, render_template, send_file, request
from dotenv import load_dotenv

# Share the AI API's .env so Supabase credentials are configured in one place.
load_dotenv(Path(__file__).resolve().parent.parent / "ai-agents" / ".env")

try:
    from supabase import create_client

    _sb_url = os.getenv("SUPABASE_URL")
    _sb_key = os.getenv("SUPABASE_KEY")
    supabase = create_client(_sb_url, _sb_key) if _sb_url and _sb_key else None
except Exception:
    supabase = None


# This Flask app serves the marketing/frontend pages.
# It expects templates/ and static/ to live alongside this file.
BASE_DIR = Path(__file__).resolve().parent.parent

app = Flask(__name__)  # looks for templates/ and static/ in the same folder as app.py


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/form")
def form():
    return render_template("form.html")


# Featured example videos shown on the landing page carousel. Scores are read
# live from Supabase when the video has been analyzed; otherwise the card shows
# "Not yet scored" rather than a fabricated number.
FEATURED_VIDEOS = [
    "https://www.youtube.com/watch?v=HNiFC1aVBa0",
    "https://www.youtube.com/watch?v=21_KQbzw6K4",
    "https://www.youtube.com/watch?v=foYPoIj4wlM",
    "https://www.youtube.com/watch?v=JD28VAUCfO0",
    "https://www.youtube.com/watch?v=Hf9SI76pRbQ",
]


def _dev_to_ten(dev_score):
    if dev_score is None:
        return None
    return max(1, min(10, round(float(dev_score) / 10)))


def _featured_with_scores():
    """Pair each featured video with its real dev score from Supabase (or None)."""
    scores = {}
    if supabase is not None:
        try:
            resp = (
                supabase.table("video_eval")
                .select("video_path, dev_score")
                .in_("video_path", FEATURED_VIDEOS)
                .execute()
            )
            for row in resp.data or []:
                scores[row["video_path"]] = row.get("dev_score")
        except Exception:
            pass
    cards = []
    for url in FEATURED_VIDEOS:
        vid = url.split("v=")[-1]
        cards.append({
            "embed": f"https://www.youtube.com/embed/{vid}",
            "ten": _dev_to_ten(scores.get(url)),
        })
    return cards


# Section partials, loaded into index.html via fetch(). Served explicitly
# because Flask does not expose the raw templates/ directory.
@app.route("/partials/<name>")
def partial(name):
    allowed = {"metrics", "shows", "extension"}
    if name not in allowed:
        return ("Not found", 404)
    if name == "shows":
        return render_template("shows.html", cards=_featured_with_scores())
    return render_template(f"{name}.html")

MINDSAFE_API_URL = os.getenv("MINDSAFE_API_URL", "http://localhost:5001")


@app.route("/analyze")
def analyze():
    """
    Real evaluation flow: take a YouTube URL, call the MindSafe API
    (metadata mode — server-side download is blocked by YouTube, so the web
    app uses the title-based estimate), poll for the result, and render it.

    For full transcript analysis, users install the Chrome extension, which
    fetches captions / runs in-browser Whisper from their own session.
    """
    url = (request.args.get("url") or "").strip()
    if not url:
        return render_template("results.html", error="Please enter a YouTube URL.")

    import time
    import requests

    # Derive a title from the URL for the metadata estimate. The extension
    # passes the real page title; from the web app we only have the URL, so we
    # send the video id and let the API/LLM work from that.
    try:
        age = float(request.args.get("age", 6))
    except ValueError:
        age = 6.0

    try:
        submit = requests.post(
            f"{MINDSAFE_API_URL}/evaluate/metadata",
            json={"title": url, "age": age, "url": url},
            timeout=10,
        )
        submit.raise_for_status()
        job_id = submit.json()["job_id"]
    except Exception as e:
        return render_template("results.html", error=f"Could not reach the analysis service: {e}")

    # Poll for completion (metadata mode is fast, a few seconds).
    result = None
    for _ in range(20):
        time.sleep(1)
        try:
            poll = requests.get(f"{MINDSAFE_API_URL}/evaluate/{job_id}", timeout=10)
            job = poll.json()
        except Exception:
            continue
        if job.get("status") == "done":
            result = job.get("result")
            break
        if job.get("status") == "failed":
            return render_template("results.html", error=job.get("error", "Analysis failed."))

    if result is None:
        return render_template("results.html", error="Analysis timed out. Please try again.")

    overall = result.get("overall_scores", {})
    dev = overall.get("development_score")
    return render_template(
        "results.html",
        url=url,
        dev_score=dev,
        ten=(max(1, min(10, round(dev / 10))) if dev is not None else None),
        brainrot=overall.get("brainrot_index"),
        interp=result.get("interpretations", {}),
        summary=result.get("parent_summary"),
        mode=result.get("metadata", {}).get("analysis_mode"),
        note=result.get("metadata", {}).get("note"),
    )


@app.route("/history")
def history():
    """Past evaluations, read from the Supabase video_eval table."""
    rows = []
    error = None
    if supabase is None:
        error = "Supabase is not configured (set SUPABASE_URL / SUPABASE_KEY in ai-agents/.env)."
    else:
        try:
            resp = (
                supabase.table("video_eval")
                .select(
                    "video_path, child_age, dev_score, brainrot_index, "
                    "overall_recommendation, duration_minutes"
                )
                .order("video_path")
                .limit(200)
                .execute()
            )
            rows = resp.data or []
        except Exception as e:
            error = f"Could not load history: {e}"
    return render_template("history.html", rows=rows, error=error)


@app.route("/download-extension")
def download_extension():
    """
    Create a ZIP of the chrome_extension folder on the fly and return it.

    This lets the user click a single download button on the frontend page
    and receive the unpacked Chrome extension as a zip file.
    """
    extension_dir = BASE_DIR / "chrome_extension"
    if not extension_dir.exists():
        return (
            "chrome_extension folder not found on server",
            500,
            {"Content-Type": "text/plain"},
        )

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in extension_dir.rglob("*"):
            if path.is_file():
                arcname = Path("chrome_extension") / path.relative_to(extension_dir)
                zf.write(path, arcname)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="mindsafe-chrome-extension.zip",
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
