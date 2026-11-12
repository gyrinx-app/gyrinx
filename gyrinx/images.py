"""Validate, centre-crop and resize uploaded account, model and gang pictures.

Store model portraits and gang landscapes at the aspect ratios expected
by every display. Enforce those ratios on the server even when the
browser cropper is unavailable or bypassed.

Forms reject non-images. Decode fully here to reject truncated or otherwise
corrupt image files before storing them.
"""

from io import BytesIO
from typing import NamedTuple

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps


class Ratio(NamedTuple):
    """An aspect ratio shared by server crops and browser cropper attributes."""

    across: int
    down: int

    def __str__(self):
        return f"{self.across}:{self.down}"


#: A model's picture: portrait, four wide to five tall.
PORTRAIT = Ratio(4, 5)
#: An account picture, displayed inside a circular frame.
SQUARE = Ratio(1, 1)
#: A gang's picture: landscape, sixteen wide to nine tall.
LANDSCAPE = Ratio(16, 9)

#: Maximum stored dimension, covering the largest card and page display.
MAX_PX = 1600


def to_shape(upload, ratio):
    """Return a JPEG upload cropped to ratio and bounded by MAX_PX.

    Apply EXIF orientation before choosing the crop so rotated phone images
    use the correct dimensions.
    """
    try:
        with Image.open(upload) as source:
            image = ImageOps.exif_transpose(source)
            image = ImageOps.fit(
                _flattened(image),
                _fitted(image.size, ratio),
                method=Image.Resampling.LANCZOS,
            )
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88)
    except OSError as broken:
        # Header validation can accept truncated images. Reject full-decode errors here.
        raise ValidationError(
            "That picture could not be read — the file may be cut short "
            "or damaged. Try uploading it again."
        ) from broken
    name = upload.name.rsplit(".", 1)[0] + ".jpg"
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def _flattened(image):
    """Composite transparency onto white before JPEG conversion.

    Discarding alpha alone can reveal hidden palette or editor pixel colours.
    """
    if image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        image = image.convert("RGBA")
        ground = Image.new("RGB", image.size, (255, 255, 255))
        ground.paste(image, mask=image.getchannel("A"))
        return ground
    return image.convert("RGB")


def _fitted(size, ratio):
    """Find the largest bounded crop using whole multiples of the ratio dimensions."""
    width, height = size
    across, down = ratio
    times = int(min(width / across, height / down))
    cap = MAX_PX // max(across, down)
    times = max(1, min(times, cap))
    return (across * times, down * times)
