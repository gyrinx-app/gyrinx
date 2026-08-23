"""Uploaded pictures, brought to the shape their surfaces draw.

A model's picture is portrait, a gang's is landscape, and every surface
that draws one — the card's dropdown, the printed card, the lore page —
assumes the ratio rather than measuring the file. So the shape is
settled here, once, on the way in: whatever arrives is centre-cropped
to the ratio and capped in size, and what is stored is always drawable.

The browser offers a nicer version of the same act — panning and
zooming the crop before upload — but what it sends is still just a
file, and nothing obliges it to have run. This is the rule; the
browser's chooser is a courtesy. A file that is not an image at all is
the form's refusal; one that only *opens* as an image and breaks on the
full decode — a truncated transfer — is refused here, because this is
where the full decode happens.
"""

from io import BytesIO
from typing import NamedTuple

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps


class Ratio(NamedTuple):
    """A picture's shape, width to height, spelt ``4:5`` where drawn.

    One constant serves every layer: the crop here works on the pair,
    and a template stamps ``str(ratio)`` onto the browser's crop dialog
    — so the window the dialog offers and the shape the server enforces
    cannot come apart.
    """

    across: int
    down: int

    def __str__(self):
        return f"{self.across}:{self.down}"


#: A model's picture: portrait, four wide to five tall.
PORTRAIT = Ratio(4, 5)
#: A gang's picture: landscape, sixteen wide to nine tall.
LANDSCAPE = Ratio(16, 9)

#: The long side of a stored picture. Phone photographs arrive at many
#: times this; a card, a print sheet and a lore page never draw one
#: bigger.
MAX_PX = 1600


def to_shape(upload, ratio):
    """One picture, centre-cropped to ``ratio`` and capped at ``MAX_PX``.

    Returns a fresh upload carrying JPEG bytes under the original name.
    EXIF rotation is applied first — a phone photograph's pixels are
    often stored sideways with a tag saying so, and a crop that ignored
    the tag would take its window from the wrong axis.
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
        # Opens as an image, breaks on the full decode: a truncated
        # transfer. The validation layer's own check stops at the
        # header, so the refusal is made here, as a refusal.
        raise ValidationError(
            "That picture could not be read — the file may be cut short "
            "or damaged. Try uploading it again."
        ) from broken
    name = upload.name.rsplit(".", 1)[0] + ".jpg"
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def _flattened(image):
    """The picture on an opaque white ground, ready to become a JPEG.

    Dropping the alpha channel instead would keep whatever colour sat
    under the transparent pixels — black for palette images, leftovers
    for editor exports — and print it.
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
    """The largest ``ratio``-shaped box the picture can fill, capped.

    Whole multiples of the ratio pair, so the stored shape is the ratio
    exactly — rounding each side on its own drifts on small pictures,
    and the surfaces drawing these assume the shape rather than
    measuring the file. The pair is coprime, so multiples lose at most
    a sliver of a ratio-step off each edge.
    """
    width, height = size
    across, down = ratio
    times = int(min(width / across, height / down))
    cap = MAX_PX // max(across, down)
    times = max(1, min(times, cap))
    return (across * times, down * times)
