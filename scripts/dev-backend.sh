#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
uv sync --dev
DATA_DIR="${DATA_DIR:-./data}" \
INFERENCE_BACKEND="${INFERENCE_BACKEND:-mock}" \
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT:-8000}"
