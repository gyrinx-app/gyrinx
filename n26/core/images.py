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
the form's refusal, not ours: ``ImageField`` has already said no by the
time this runs.
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps

#: A model's picture: portrait, four wide to five tall.
PORTRAIT = (4, 5)
#: A gang's picture: landscape, sixteen wide to nine tall.
LANDSCAPE = (16, 9)

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
    with Image.open(upload) as source:
        image = ImageOps.exif_transpose(source)
        image = ImageOps.fit(
            image.convert("RGB"),
            _fitted(image.size, ratio),
            method=Image.Resampling.LANCZOS,
        )
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    name = upload.name.rsplit(".", 1)[0] + ".jpg"
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


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
