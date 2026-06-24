#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
uv sync --dev
DATA_DIR="${DATA_DIR:-./data}" \
INFERENCE_BACKEND="${INFERENCE_BACKEND:-ultralytics}" \
MODEL_PATH="${MODEL_PATH:-./yolo11n.pt}" \
DEVICE="${DEVICE:-0}" \
RUN_TASKS_INLINE="${RUN_TASKS_INLINE:-true}" \
TASK_WORKER_ENABLED="${TASK_WORKER_ENABLED:-false}" \
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "${PORT:-8010}"
