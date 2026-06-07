from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import get_storage_service, get_store
from app.models.schemas import Asset
from app.repositories.json_store import JsonStore
from app.services.storage_service import StorageService


router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.post("/upload", response_model=Asset)
def upload_asset(
    file: UploadFile = File(...),
    storage: StorageService = Depends(get_storage_service),
    store: JsonStore = Depends(get_store),
) -> Asset:
    asset = storage.save_upload(file)
    return store.create_asset(asset)


@router.get("", response_model=list[Asset])
def list_assets(store: JsonStore = Depends(get_store)) -> list[Asset]:
    return store.list_assets()


@router.get("/{asset_id}", response_model=Asset)
def get_asset(asset_id: str, store: JsonStore = Depends(get_store)) -> Asset:
    asset = store.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return asset
