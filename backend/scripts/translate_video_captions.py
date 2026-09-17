"""Backfill English captions for video frames using a local Ollama model.

Walks every batch/video/frame in the database and translates the Chinese
``description_text`` of frames whose ``description_en`` is still empty, so the
script is resumable: re-running it only picks up what is left.

Example:
    python scripts/translate_video_captions.py --model qwen3:14b
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.dependencies import get_store
from app.models.schemas import VideoCaptionFrame


DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"
DEFAULT_CHUNK_SIZE = 15
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 600.0

SYSTEM_PROMPT = """你是铁路巡检领域的专业翻译。用户会给出一组编号的中文图像描述，你需要把每条翻译成简洁、准确的英文。

要求：
1. 逐条翻译，保持编号一一对应，不增不减。
2. 使用铁路行业标准术语，参考术语表：
   接触网=catenary；承力索=messenger wire；吊弦=dropper；腕臂=cantilever；
   绝缘子=insulator；接触网支柱=catenary mast；轨道=track；钢轨=rail；
   道岔=turnout；扣件=fastener；轨枕=sleeper；道床=ballast bed；
   侵限=clearance intrusion；限界=clearance；路基=subgrade；桥梁=bridge；
   隧道=tunnel；信号机=signal；防护栏=protective fence；作业人员=workers；
   安全帽=safety helmet；反光背心=reflective vest；防护服=protective clothing；
   施工=construction；大型机械=heavy machinery；挖掘机=excavator；吊车=crane；
   电力机车=electric locomotive；捣固车=tamping machine。
3. 译文保持描述性、客观，不添加原文没有的信息，不做解释或补充说明。
4. 只输出 JSON 对象，键是编号字符串，值是英文译文，不要输出任何其他内容。

输出格式示例：{"1": "Two workers in reflective vests inspect the catenary mast.", "2": "Ballast bed with missing fasteners."}"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate Chinese video frame captions to English with a local Ollama model.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--batch-name", default="", help="Only translate frames of this batch (default: every batch).")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--limit-frames", type=int, default=None, help="Stop after translating this many frames (dry runs).")
    parser.add_argument("--force", action="store_true", help="Re-translate frames that already have an English caption.")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be greater than 0")

    settings = get_settings()
    store = get_store()

    batches = store.list_video_caption_batches()
    if args.batch_name.strip():
        wanted = args.batch_name.strip()
        batches = [batch for batch in batches if batch.name == wanted]
        if not batches:
            raise SystemExit(f"batch not found: {wanted}")

    pending: list[VideoCaptionFrame] = []
    for batch in batches:
        for video in store.list_video_caption_videos(batch.batch_id):
            if args.force:
                frames, _ = store.list_video_caption_frames(video.video_id, page=1, page_size=100000)
                pending.extend(frame for frame in frames if frame.description_text.strip())
            else:
                pending.extend(store.list_video_caption_frames_missing_english(video.video_id))

    if args.limit_frames is not None:
        pending = pending[: args.limit_frames]

    if not pending:
        print("Nothing to translate: every frame already has an English caption.", flush=True)
        return

    print(
        f"Model {args.model} @ {args.ollama_url}: {len(pending)} frame(s) to translate, chunk size {args.chunk_size}",
        flush=True,
    )

    client = httpx.Client(timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=settings.ollama_timeout_seconds))
    translated = 0
    failed = 0
    started = time.monotonic()
    chunk_count = 0

    try:
        for offset in range(0, len(pending), args.chunk_size):
            chunk = pending[offset : offset + args.chunk_size]
            chunk_count += 1
            chunk_started = time.monotonic()

            translations = _translate_chunk(client, args.ollama_url, args.model, chunk)
            if translations is None:
                failed += len(chunk)
                print(f"[chunk {chunk_count}] failed after {MAX_ATTEMPTS} attempts, skipped {len(chunk)} frame(s)", flush=True)
            else:
                for index, frame in enumerate(chunk, start=1):
                    text = (translations.get(str(index)) or "").strip()
                    if not text:
                        failed += 1
                        continue
                    if store.update_video_caption_frame_description_en(frame.frame_id, text):
                        translated += 1
                print(
                    f"[chunk {chunk_count}] {len(chunk)} frame(s) in {time.monotonic() - chunk_started:.1f}s "
                    f"| done={translated} failed={failed}",
                    flush=True,
                )

            if chunk_count % 10 == 0:
                elapsed = time.monotonic() - started
                rate = translated / elapsed if elapsed else 0.0
                remaining = len(pending) - translated - failed
                eta_minutes = (remaining / rate / 60) if rate > 0 else 0.0
                print(
                    f"== progress: {translated + failed}/{len(pending)} frame(s), {rate:.2f} frame/s, "
                    f"ETA {eta_minutes:.1f} min ==",
                    flush=True,
                )
    finally:
        client.close()

    elapsed = time.monotonic() - started
    print(
        f"Finished: translated={translated} failed={failed} total={len(pending)} in {elapsed / 60:.1f} min",
        flush=True,
    )


def _translate_chunk(
    client: httpx.Client,
    ollama_url: str,
    model: str,
    chunk: list[VideoCaptionFrame],
) -> dict[str, str] | None:
    listing = "\n".join(f"{index}. {frame.description_text.strip()}" for index, frame in enumerate(chunk, start=1))
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.2},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"请翻译以下 {len(chunk)} 条描述：\n{listing}"},
        ],
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.post(f"{ollama_url.rstrip('/')}/api/chat", json=payload)
            response.raise_for_status()
            content = (response.json().get("message") or {}).get("content") or ""
            translations = _parse_translations(content)
            if translations:
                return translations
            print(f"  attempt {attempt}: model returned no usable JSON ({content[:120]!r})", flush=True)
        except Exception as exc:
            print(f"  attempt {attempt}: {type(exc).__name__}: {exc}", flush=True)
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return None


def _parse_translations(content: str) -> dict[str, str]:
    """Pull a ``{"1": "..."}`` mapping out of a model reply."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    parsed = _loads(text)
    if parsed is None:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        parsed = _loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        return {}

    translations: dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(value, str) and value.strip():
            translations[str(key).strip()] = value.strip()
        elif isinstance(value, dict):
            nested = value.get("en") or value.get("english") or value.get("translation")
            if isinstance(nested, str) and nested.strip():
                translations[str(key).strip()] = nested.strip()
    return translations


def _loads(text: str) -> object | None:
    try:
        return json.loads(text)
    except Exception:
        return None


if __name__ == "__main__":
    main()
