
import io
import warnings

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MiB
MAX_IMAGE_PIXELS = 20_000_000

ALLOWED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


async def validate_image(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_FORMATS.values():
        raise HTTPException(
            status_code=400,
            detail="Only JPEG, PNG or WebP images allowed",
        )

    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds 5 MB limit",
        )

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Empty image upload",
        )

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(io.BytesIO(image_bytes)) as image:
                if image.format not in ALLOWED_FORMATS:
                    raise ValueError("Unsupported image format")

                if ALLOWED_FORMATS[image.format] != file.content_type:
                    raise ValueError("Image format does not match MIME type")

                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError("Image dimensions exceed allowed limit")

                image.verify()

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid or unsupported image",
        )

    return image_bytes
