"""Every stored picture holds its surface's shape, whatever arrived."""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from n26.core.images import LANDSCAPE, MAX_PX, PORTRAIT, to_shape


def upload_of(width, height, name="shot.png"):
    buffer = BytesIO()
    Image.new("RGB", (width, height), "orange").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def size_of(upload):
    with Image.open(upload) as image:
        return image.size


class TestTheShape:
    def test_a_wide_shot_comes_out_portrait(self):
        width, height = size_of(to_shape(upload_of(1000, 500), PORTRAIT))
        assert width / height == PORTRAIT[0] / PORTRAIT[1]

    def test_a_tall_shot_comes_out_landscape(self):
        width, height = size_of(to_shape(upload_of(500, 1000), LANDSCAPE))
        assert abs(width / height - LANDSCAPE[0] / LANDSCAPE[1]) < 0.01

    def test_an_already_shaped_picture_keeps_its_pixels(self):
        assert size_of(to_shape(upload_of(400, 500), PORTRAIT)) == (400, 500)


class TestTheCap:
    def test_a_huge_photograph_is_brought_down(self):
        width, height = size_of(to_shape(upload_of(4000, 6000), PORTRAIT))
        assert max(width, height) <= MAX_PX

    def test_a_small_picture_is_never_blown_up(self):
        width, height = size_of(to_shape(upload_of(80, 100), PORTRAIT))
        assert max(width, height) == 100


class TestTheFile:
    def test_the_result_is_jpeg_under_the_old_name(self):
        shaped = to_shape(upload_of(500, 500, name="vesna.png"), PORTRAIT)
        assert shaped.name == "vesna.jpg"
        with Image.open(shaped) as image:
            assert image.format == "JPEG"
