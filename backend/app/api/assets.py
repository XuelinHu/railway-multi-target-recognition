from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import get_storage_service, get_store
from app.models.schemas import Asset
from app.repositories.postgres_store import PostgresStore
from app.services.storage_service import StorageService


router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.post("/upload", response_model=dict)
def upload_asset(
    file: UploadFile = File(...),
    storage: StorageService = Depends(get_storage_service),
    store: PostgresStore = Depends(get_store),
) -> dict:
    asset = storage.save_upload(file)
    return _public_asset(store.create_asset(asset))


@router.get("", response_model=list[dict])
def list_assets(store: PostgresStore = Depends(get_store)) -> list[dict]:
    return [_public_asset(asset) for asset in store.list_assets()]


@router.get("/{asset_id}", response_model=dict)
def get_asset(asset_id: str, store: PostgresStore = Depends(get_store)) -> dict:
    asset = store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return _public_asset(asset)


def _public_asset(asset: Asset) -> dict:
    public = {
        "id": asset.id,
        "filename": asset.filename,
        "content_type": asset.content_type,
        "type": asset.type,
        "size_bytes": asset.size_bytes,
        "created_at": asset.created_at,
    }
    if asset.type == "image":
        public.update(width=asset.width, height=asset.height)
    return public


@router.get("/{asset_id}/frames/{frame_index}/image")
def get_frame_image(
    asset_id: str,
    frame_index: int,
    storage: StorageService = Depends(get_storage_service),
    store: PostgresStore = Depends(get_store),
) -> FileResponse:
    if store.get_asset(asset_id) is None:
        raise HTTPException(status_code=404, detail="asset not found")
    frame_path = storage.frame_path(asset_id, frame_index)
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail="frame image not found")
    return FileResponse(frame_path, media_type="image/jpeg")
