from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_store
from app.models.schemas import AnnotationsDocument, now_utc
from app.repositories.json_store import JsonStore


router = APIRouter(prefix="/api/assets", tags=["annotations"])


@router.get("/{asset_id}/annotations", response_model=AnnotationsDocument)
def get_annotations(asset_id: str, store: JsonStore = Depends(get_store)) -> AnnotationsDocument:
    annotations = store.get_annotations(asset_id)
    if annotations is None:
        raise HTTPException(status_code=404, detail="annotations not found")
    return annotations


@router.put("/{asset_id}/annotations", response_model=AnnotationsDocument)
def save_annotations(
    asset_id: str,
    annotations: AnnotationsDocument,
    store: JsonStore = Depends(get_store),
) -> AnnotationsDocument:
    if store.get_asset(asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if annotations.asset_id != asset_id:
        raise HTTPException(status_code=400, detail="asset_id mismatch")
    annotations.updated_at = now_utc()
    return store.save_annotations(annotations)
