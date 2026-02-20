from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlmodel import Session

import os

from app.s3_client import presigned_url, upload_image
from app.db import get_session
from app.routers.auth import require_any_permission, require_permission

router = APIRouter(prefix="/api/media", tags=["media"])


@router.post("/upload")
def upload_media(
    request: Request,
    kind: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    require_any_permission(request, session, ["quality_checks", "assembly_line", "orders"], "write")
    folder = os.getenv("S3_FIRST_PART_FOLDER", "qc/first-part")
    if kind == "dispatch":
        folder = os.getenv("S3_DISPATCH_FOLDER", "qc/dispatch")
    elif kind != "first_part":
        raise HTTPException(status_code=400, detail="Invalid upload kind")

    try:
        key = upload_image(file.file, folder=folder)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return JSONResponse(
        {
            "public_id": key,
        }
    )


@router.get("/signed-url")
def get_signed_url(
    request: Request,
    public_id: str,
    resource_type: str = "image",
    session: Session = Depends(get_session),
):
    require_permission(request, session, "quality_checks", "read")
    try:
        url = presigned_url(public_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"url": url}
