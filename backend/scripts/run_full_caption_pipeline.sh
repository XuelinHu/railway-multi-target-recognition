#!/usr/bin/env bash
#
# Overnight video-captioning pipeline. Three stages, run back to back:
#
#   1. Frame extraction + Chinese captions with DeepSeek-VL2 (needs the GPU to itself)
#   2. English captions backfilled with the local Ollama model (chat comes back online here)
#   3. Keyword + title refresh for every batch
#
# Stage 1 cannot share the 24GB card with Ollama, so the script unloads the chat
# model first. Any other process holding VRAM (for example a backend API server
# that already ran a caption task) must be restarted by hand before launching.
#
# Usage:
#   nohup backend/scripts/run_full_caption_pipeline.sh > logs/pipeline.log 2>&1 &
#   tail -f logs/pipeline.log
#
# Re-running is safe: captioned frames and translated frames are skipped, so the
# pipeline resumes where it stopped.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"
PYTHON="${BACKEND_DIR}/.venv/bin/python"
LOG_DIR="${REPO_DIR}/logs"

SOURCE_DIR="${SOURCE_DIR:-/ds2/videos/DJI_001}"
BATCH_NAME="${BATCH_NAME:-}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:14b}"
MIN_FREE_MIB="${MIN_FREE_MIB:-9000}"

mkdir -p "${LOG_DIR}"
cd "${BACKEND_DIR}"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }

free_mib() {
    nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' '
}

log "Pipeline starting (source=${SOURCE_DIR}, batch=${BATCH_NAME:-<directory name>})"

# --- Free the GPU -----------------------------------------------------------------
if command -v ollama >/dev/null 2>&1; then
    log "Unloading Ollama model ${OLLAMA_MODEL} to free VRAM"
    ollama stop "${OLLAMA_MODEL}" >/dev/null 2>&1 || log "  ollama stop reported a problem; continuing"
else
    log "ollama CLI not found; assuming no chat model is resident"
fi

FREE="$(free_mib || true)"
log "GPU free memory: ${FREE:-unknown} MiB (stage 1 needs at least ${MIN_FREE_MIB} MiB; it waits rather than exiting)"
if [[ -n "${FREE}" && "${FREE}" -lt "${MIN_FREE_MIB}" ]]; then
    log "GPU is busy right now - stage 1 will block until ${MIN_FREE_MIB} MiB frees up. Ctrl-C and free the GPU if that is unexpected."
fi

# --- Stage 1: frame extraction + Chinese captions ---------------------------------
log "=== Stage 1/3: frame extraction + Chinese captions ==="
CAPTION_ARGS=(--source-dir "${SOURCE_DIR}" --min-free-mib "${MIN_FREE_MIB}" --wait-for-vram)
if [[ -n "${BATCH_NAME}" ]]; then
    CAPTION_ARGS+=(--batch-name "${BATCH_NAME}")
fi
if ! "${PYTHON}" scripts/process_video_captions.py "${CAPTION_ARGS[@]}" 2>&1 | tee "${LOG_DIR}/pipeline-caption.log"; then
    log "ERROR: stage 1 failed; see ${LOG_DIR}/pipeline-caption.log"
    exit 1
fi
log "=== Stage 1/3 done ==="

# --- Stage 2: English captions ----------------------------------------------------
log "=== Stage 2/3: English translation via ${OLLAMA_MODEL} ==="
TRANSLATE_ARGS=(--model "${OLLAMA_MODEL}")
if [[ -n "${BATCH_NAME}" ]]; then
    TRANSLATE_ARGS+=(--batch-name "${BATCH_NAME}")
fi
if ! "${PYTHON}" scripts/translate_video_captions.py "${TRANSLATE_ARGS[@]}" 2>&1 | tee "${LOG_DIR}/pipeline-translate.log"; then
    log "ERROR: stage 2 failed; see ${LOG_DIR}/pipeline-translate.log"
    exit 1
fi
log "=== Stage 2/3 done ==="

# --- Stage 3: keywords + titles ---------------------------------------------------
log "=== Stage 3/3: keyword and title refresh ==="
if ! "${PYTHON}" scripts/update_video_caption_titles.py 2>&1 | tee "${LOG_DIR}/pipeline-titles.log"; then
    log "ERROR: stage 3 failed; see ${LOG_DIR}/pipeline-titles.log"
    exit 1
fi
log "=== Stage 3/3 done ==="

log "Pipeline finished successfully"
