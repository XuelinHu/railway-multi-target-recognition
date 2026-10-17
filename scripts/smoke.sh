#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
uv sync --dev
DATA_DIR="$(mktemp -d)" INFERENCE_BACKEND=mock RUN_TASKS_INLINE=true uv run pytest
