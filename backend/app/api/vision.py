from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import get_vision_service
from app.services.vision_service import VisionFeature, VisionService

router = APIRouter(prefix="/api/vision", tags=["vision"])


@router.post("/analyze")
def analyze_image(
    feature: VisionFeature,
    model_name: str | None = None,
    file: UploadFile = File(...),
    service: VisionService = Depends(get_vision_service),
) -> dict[str, Any]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image uploads supported")
    try:
        return service.analyze_upload(file, feature, model_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
