from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha1

import httpx
import jieba.posseg as pseg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import require_admin
from app.core.dependencies import get_store
from app.models.schemas import ApiResponse, AuthUser, LabelConfigCreateRequest, LabelConfigUpdateRequest
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/labels", tags=["labels"])

VIDEO_TERM_STOPWORDS = {
    "场景", "画面", "背景", "目标", "图片", "环境", "整体", "字样", "颜色", "附近", "一侧", "一些",
    "前方", "后方", "左侧", "右侧", "上方", "下方", "部分", "位置", "方向", "情况", "过程", "时候",
    "黄色", "黑色", "白色", "蓝色", "红色",
}


@router.get("")
def list_labels(store: PostgresStore = Depends(get_store)) -> ApiResponse:
    labels = store.list_label_configs()
    return ApiResponse(data=[label.model_dump(mode="json", by_alias=True) for label in labels])


@router.get("/search")
def search_labels(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    query: str = Query(default=""),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    labels, total = store.list_label_configs_page(page, page_size, query.strip())
    return ApiResponse(data={"records": [label.model_dump(mode="json", by_alias=True) for label in labels], "total": total})


@router.get("/video-term-candidates")
def video_term_candidates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100, alias="pageSize"),
    query: str = Query(default=""),
    store: PostgresStore = Depends(get_store),
) -> ApiResponse:
    counts: Counter[str] = Counter()
    for description in store.list_video_caption_descriptions():
        for token in pseg.cut(description):
            word = token.word.strip()
            if (
                token.flag.startswith("n")
                and 2 <= len(word) <= 8
                and word not in VIDEO_TERM_STOPWORDS
                and any("\u4e00" <= char <= "\u9fff" for char in word)
            ):
                counts[word] += 1
    known = {label.chinese_name for label in store.list_label_configs()}
    normalized = query.strip()
    candidates = [
        {"chineseName": word, "englishName": f"rail_term_{sha1(word.encode()).hexdigest()[:10]}", "occurrences": count}
        for word, count in counts.most_common()
        if count >= 2 and word not in known and (not normalized or normalized in word)
    ]
    start = (page - 1) * page_size
    return ApiResponse(data={"records": candidates[start : start + page_size], "total": len(candidates)})


@router.post("")
def create_label(request: LabelConfigCreateRequest, store: PostgresStore = Depends(get_store), _: AuthUser = Depends(require_admin)) -> ApiResponse:
    try:
        label = store.create_label_config(
            english_name=request.english_name,
            chinese_name=request.chinese_name,
            description=request.description,
            copy_from_label_id=request.copy_from_label_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="标签数据不合法") from exc
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.post("/{label_id}/copy")
def copy_label(label_id: int, store: PostgresStore = Depends(get_store), _: AuthUser = Depends(require_admin)) -> ApiResponse:
    label = store.copy_label_config(label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.put("/{label_id}")
def update_label(
    label_id: int,
    request: LabelConfigUpdateRequest,
    store: PostgresStore = Depends(get_store),
    _: AuthUser = Depends(require_admin),
) -> ApiResponse:
    try:
        label = store.update_label_config(
            label_id=label_id,
            english_name=request.english_name,
            chinese_name=request.chinese_name,
            description=request.description,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail="标签数据不合法") from exc
    if label is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data=label.model_dump(mode="json", by_alias=True))


@router.delete("/{label_id}")
def delete_label(label_id: int, store: PostgresStore = Depends(get_store), _: AuthUser = Depends(require_admin)) -> ApiResponse:
    deleted = store.delete_label_config(label_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="标签不存在")
    return ApiResponse(data={"deleted": True})


@router.post("/{label_id}/thumbnail")
def find_label_thumbnail(
    label_id: int,
    store: PostgresStore = Depends(get_store),
    _: AuthUser = Depends(require_admin),
) -> ApiResponse:
    label = next((item for item in store.list_label_configs() if item.label_id == label_id), None)
    if label is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    thumbnail = _search_commons_thumbnail(label)
    if not thumbnail:
        raise HTTPException(status_code=404, detail="未找到可用缩略图")
    updated = store.update_label_thumbnail(label_id, thumbnail)
    return ApiResponse(data=updated.model_dump(mode="json", by_alias=True))


@router.post("/thumbnails/lookup")
def find_missing_label_thumbnails(
    store: PostgresStore = Depends(get_store),
    _: AuthUser = Depends(require_admin),
) -> ApiResponse:
    missing = [label for label in store.list_label_configs() if not label.thumbnail_url]
    with ThreadPoolExecutor(max_workers=4) as executor:
        matches = list(executor.map(_search_commons_thumbnail, missing))
    updated = []
    for label, thumbnail in zip(missing, matches):
        if thumbnail:
            result = store.update_label_thumbnail(label.label_id, thumbnail)
            if result:
                updated.append(result.model_dump(mode="json", by_alias=True))
    return ApiResponse(data={"updated": updated, "searched": len(missing), "found": len(updated)})


def _search_commons_thumbnail(label) -> str:
    english = label.english_name.replace("_", " ")
    terms = [f"filetype:bitmap {label.chinese_name}", f"filetype:bitmap railway {english}"]
    for term in terms:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": term,
            "gsrnamespace": "6",
            "gsrlimit": "1",
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": "160",
            "format": "json",
        }
        try:
            response = httpx.get(
                "https://commons.wikimedia.org/w/api.php",
                params=params,
                headers={"User-Agent": "RailwayRecognition/1.0 (rail inspection tag thumbnail lookup)"},
                timeout=12,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            info = (page.get("imageinfo") or [{}])[0]
            thumbnail = str(info.get("thumburl") or info.get("url") or "")
            if thumbnail:
                return thumbnail
        except Exception:
            continue
    return ""
