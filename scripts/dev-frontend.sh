#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../frontend"
npm install
VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:8010}" \
npm run dev -- --host 0.0.0.0 --port "${PORT:-4004}"
