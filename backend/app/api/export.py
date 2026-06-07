from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.dependencies import get_export_service
from app.services.export_service import ExportService


router = APIRouter(prefix="/api/assets", tags=["export"])


@router.get("/{asset_id}/export")
def export_annotations(
    asset_id: str,
    format: Literal["json", "coco", "yolo"] = "json",
    export_service: ExportService = Depends(get_export_service),
):
    annotations = export_service.get_annotations(asset_id)
    if annotations is None:
        raise HTTPException(status_code=404, detail="annotations not found")
    if format == "json":
        return JSONResponse(annotations.model_dump(mode="json"))
    if format == "coco":
        return JSONResponse(export_service.to_coco(annotations))
    return PlainTextResponse(export_service.to_yolo_text(annotations), media_type="text/plain")
