"""Helpers for validating uploaded images."""

from typing import Tuple

from fastapi import HTTPException, UploadFile, status

from ..config.settings import settings


def sniff_image_type(data: bytes) -> str:
    """Identify the image format from its magic bytes (never trust the client's header)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "image/heic"
    return ""


async def read_image_upload(file: UploadFile) -> Tuple[bytes, str]:
    """Read an uploaded image with a size cap; returns (bytes, mime_type)."""
    limit = settings.max_upload_bytes
    chunks, total = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Image is too large (max {settings.max_upload_mb} MB).",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    mime = sniff_image_type(data)
    if not mime:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported image format. Please upload a JPEG, PNG, WebP or HEIC photo.",
        )
    return data, mime
