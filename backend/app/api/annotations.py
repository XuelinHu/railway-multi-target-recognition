from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_store
from app.models.schemas import AnnotationsDocument, ReviewRequest, now_utc
from app.repositories.postgres_store import PostgresStore


router = APIRouter(prefix="/api/assets", tags=["annotations"])


@router.get("/{asset_id}/annotations", response_model=AnnotationsDocument)
def get_annotations(asset_id: str, store: PostgresStore = Depends(get_store)) -> AnnotationsDocument:
    annotations = store.get_annotations(asset_id)
    if annotations is None:
        raise HTTPException(status_code=404, detail="annotations not found")
    return annotations


@router.put("/{asset_id}/annotations", response_model=AnnotationsDocument)
def save_annotations(
    asset_id: str,
    annotations: AnnotationsDocument,
    store: PostgresStore = Depends(get_store),
) -> AnnotationsDocument:
    if store.get_asset(asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if annotations.asset_id != asset_id:
        raise HTTPException(status_code=400, detail="asset_id mismatch")
    annotations.updated_at = now_utc()
    return store.save_annotations(annotations)


@router.post("/{asset_id}/annotations/review", response_model=AnnotationsDocument)
def review_annotations(
    asset_id: str,
    review: ReviewRequest,
    store: PostgresStore = Depends(get_store),
) -> AnnotationsDocument:
    annotations = store.get_annotations(asset_id)
    if annotations is None:
        raise HTTPException(status_code=404, detail="annotations not found")
    annotations.review_status = review.status
    for frame in annotations.frames:
        frame.review_status = review.status
        for obj in frame.objects:
            if review.status == "approved" and obj.status == "auto":
                obj.status = "confirmed"
            elif review.status == "rejected":
                obj.status = "rejected"
    annotations.reviewed_at = now_utc() if review.status in {"approved", "rejected"} else None
    annotations.updated_at = now_utc()
    return store.save_annotations(annotations)
