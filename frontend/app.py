import os
from pathlib import Path
from io import BytesIO
import zipfile

from flask import Flask, render_template, send_file
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


# Section partials, loaded into index.html via fetch(). Served explicitly
# because Flask does not expose the raw templates/ directory.
@app.route("/partials/<name>")
def partial(name):
    allowed = {"metrics", "shows", "extension"}
    if name not in allowed:
        return ("Not found", 404)
    return render_template(f"{name}.html")

@app.route("/loader")
def loader():
    return render_template("loader.html")
@app.route("/data")
def data():
    return render_template("data.html")


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
