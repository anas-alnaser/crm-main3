"""Safe validation of uploaded image assets (brand logos, signatures).

Rejects anything that isn't a real raster image we can decode: bad extension,
wrong MIME, oversize bytes/dimensions, unsafe filename, SVG (script vector), or
non-image content masquerading as an image.
"""
from __future__ import annotations

import os
import re

from django.conf import settings
from rest_framework import serializers

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/octet-stream",  # some browsers send this; content is still decoded
}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "asset")
    base = _SAFE_NAME.sub("_", base).strip("._") or "asset"
    return base[:120]


def validate_image_file(upload):
    """Validate an uploaded image and return ``(safe_name, hexdigest, dimensions)``.

    Raises ``serializers.ValidationError`` on any problem. Requires Pillow.
    """
    if upload is None:
        raise serializers.ValidationError("No file uploaded.")

    max_bytes = getattr(settings, "UPLOAD_MAX_IMAGE_BYTES", 5 * 1024 * 1024)
    max_dim = getattr(settings, "UPLOAD_MAX_IMAGE_DIMENSION", 4000)

    name = upload.name or ""
    ext = os.path.splitext(name.lower())[1]
    if ext == ".svg" or (upload.content_type or "").lower() == "image/svg+xml":
        raise serializers.ValidationError("SVG uploads are not allowed.")
    if ext not in ALLOWED_EXTENSIONS:
        raise serializers.ValidationError(f"Unsupported image type '{ext}'. Use PNG, JPG, or WebP.")
    if (upload.content_type or "") not in ALLOWED_CONTENT_TYPES:
        raise serializers.ValidationError(f"Unexpected content type '{upload.content_type}'.")
    if upload.size > max_bytes:
        raise serializers.ValidationError(f"Image exceeds the {max_bytes // (1024 * 1024)} MB limit.")

    import hashlib

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - Pillow is a hard dep
        raise serializers.ValidationError(f"Image processing is unavailable: {exc}")

    data = upload.read()
    upload.seek(0)
    hexdigest = hashlib.sha256(data).hexdigest()

    import io

    try:
        image = Image.open(io.BytesIO(data))
        image.verify()  # decode headers/structure; raises on non-images
        image = Image.open(io.BytesIO(data))
        width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError):
        raise serializers.ValidationError("The file could not be decoded as an image.")

    if width > max_dim or height > max_dim:
        raise serializers.ValidationError(f"Image dimensions exceed {max_dim}px.")

    return safe_filename(name), hexdigest, (width, height)
