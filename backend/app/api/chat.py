import hashlib
import inspect
import io
import json
import os
import wave
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.api.auth import require_user
from app.core.config import Settings, get_settings
from app.models.schemas import ApiResponse, AuthUser, ChatRequest, TtsRequest


router = APIRouter(prefix="/api/chat", tags=["chat"])

MAX_HISTORY_MESSAGES = 30
DEFAULT_TEMPERATURE = 0.7


@router.get("/models", response_model=ApiResponse)
def list_models(current_user: AuthUser = Depends(require_user)) -> ApiResponse:
    settings = get_settings()
    try:
        response = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5.0)
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="本地 Ollama 服务未启动或不可达，请先运行 ollama serve") from exc

    models = [
        {"name": str(item.get("name", "")), "size": int(item.get("size") or 0)}
        for item in response.json().get("models", [])
        if item.get("name")
    ]
    return ApiResponse(data={"models": models, "defaultModel": settings.ollama_default_model})


@router.post("")
def chat_stream(
    request: ChatRequest,
    current_user: AuthUser = Depends(require_user),
) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tts")
def synthesize_speech(
    request: TtsRequest,
    current_user: AuthUser = Depends(require_user),
) -> Response:
    settings = get_settings()
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="朗读文本不能为空")

    lang = request.lang or ("zh" if _contains_cjk(text) else "en")
    voice_name = settings.tts_voice_zh if lang == "zh" else settings.tts_voice_en
    cache_path = settings.tts_cache_dir / f"{hashlib.sha1(f'{voice_name}|{text}'.encode('utf-8')).hexdigest()}.wav"
    if cache_path.exists():
        return FileResponse(cache_path, media_type="audio/wav")

    audio = _synthesize_wav(_load_voice(settings, voice_name), text)
    _write_atomically(cache_path, audio)
    return Response(content=audio, media_type="audio/wav")


async def _event_stream(request: ChatRequest) -> AsyncIterator[str]:
    settings = get_settings()
    model = request.model or settings.ollama_default_model
    system_prompt = settings.chat_system_prompt_zh if request.lang == "zh" else settings.chat_system_prompt_en
    messages = [{"role": "system", "content": system_prompt}]
    messages += [{"role": item.role, "content": item.content} for item in request.messages[-MAX_HISTORY_MESSAGES:]]
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": request.temperature if request.temperature is not None else DEFAULT_TEMPERATURE,
        },
    }

    # Ollama keeps generating until done, so only the connect phase gets a deadline.
    timeout = httpx.Timeout(settings.ollama_timeout_seconds, read=None)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{settings.ollama_base_url}/api/chat",
                json=payload,
            ) as response:
                if response.status_code == 404:
                    yield _sse_event("error", {"detail": f"本地模型不存在: {model}"})
                    return
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "ignore")[:300]
                    yield _sse_event("error", {"detail": f"Ollama 返回 {response.status_code}: {body}"})
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if chunk.get("error"):
                        yield _sse_event("error", {"detail": str(chunk["error"])})
                        return

                    content = (chunk.get("message") or {}).get("content") or ""
                    if content:
                        yield _sse_event("delta", {"content": content})

                    if chunk.get("done"):
                        yield _sse_event("done", {"doneReason": chunk.get("done_reason") or "stop"})
                        return

        yield _sse_event("done", {"doneReason": "stop"})
    except httpx.ConnectError:
        yield _sse_event("error", {"detail": "本地 Ollama 服务未启动或不可达，请先运行 ollama serve"})
    except httpx.TimeoutException:
        yield _sse_event("error", {"detail": "连接本地 Ollama 超时"})
    except Exception as exc:  # noqa: BLE001 - surfaced to the browser as an SSE error event
        yield _sse_event("error", {"detail": f"对话失败: {exc}"})


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _contains_cjk(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


_voice_cache: dict[str, Any] = {}


def _load_voice(settings: Settings, voice_name: str) -> Any:
    if voice_name in _voice_cache:
        return _voice_cache[voice_name]
    try:
        from piper import PiperVoice
    except Exception as exc:
        raise HTTPException(status_code=503, detail="当前 Python 环境未安装 piper-tts，无法执行语音合成") from exc

    model_path = settings.tts_voices_dir / f"{voice_name}.onnx"
    if not model_path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"语音模型未下载: {voice_name}，请运行 "
                f"python -m piper.download_voices {voice_name} --data-dir {settings.tts_voices_dir}"
            ),
        )
    _voice_cache[voice_name] = PiperVoice.load(str(model_path))
    return _voice_cache[voice_name]


def _synthesize_wav(voice: Any, text: str) -> bytes:
    buffer = io.BytesIO()
    wav_file = wave.open(buffer, "wb")
    try:
        synthesize_wav = getattr(voice, "synthesize_wav", None)
        syn_config = _synthesis_config()
        if callable(synthesize_wav) and syn_config is not None and _accepts_keyword(synthesize_wav, "syn_config"):
            synthesize_wav(text, wav_file, syn_config=syn_config)
        elif callable(synthesize_wav):
            synthesize_wav(text, wav_file)
        else:
            voice.synthesize(text, wav_file)
    finally:
        try:
            wav_file.close()
        except Exception:  # noqa: BLE001 - header flush may fail when synthesis already raised
            pass
    return buffer.getvalue()


def _synthesis_config() -> Any | None:
    try:
        from piper import SynthesisConfig
    except Exception:
        return None
    try:
        return SynthesisConfig()
    except Exception:
        return None


def _accepts_keyword(func: Any, keyword: str) -> bool:
    try:
        return keyword in inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False


def _write_atomically(path: Any, content: bytes) -> None:
    temporary_path = path.with_suffix(".wav.tmp")
    temporary_path.write_bytes(content)
    os.replace(temporary_path, path)
