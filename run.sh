#!/bin/bash
# Start MindSafe: AI evaluation API (:5001) + website (:5000).
# Setup first: see README Quickstart.
set -e
cd "$(dirname "$0")"

trap 'kill 0' EXIT

(cd ai-agents && venv/bin/uvicorn api:app --host 127.0.0.1 --port 5001) &
(cd frontend && venv/bin/python app.py) &
wait
