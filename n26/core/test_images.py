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


class TestTheSpelling:
    """A ratio spells itself the way the crop dialog reads its
    declaration, so a template can stamp the constant straight on."""

    def test_the_pair_reads_width_to_height(self):
        assert str(PORTRAIT) == "4:5"
        assert str(LANDSCAPE) == "16:9"


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


class TestBrokenAndTransparentFiles:
    def test_a_truncated_file_is_refused_not_crashed(self):
        import pytest
        from django.core.exceptions import ValidationError

        whole = upload_of(400, 500).read()
        cut = SimpleUploadedFile("cut.png", whole[: len(whole) // 2])
        with pytest.raises(ValidationError):
            to_shape(cut, PORTRAIT)

    def test_transparency_lands_on_white(self):
        buffer = BytesIO()
        Image.new("RGBA", (400, 500), (255, 0, 0, 0)).save(buffer, format="PNG")
        clear = SimpleUploadedFile("clear.png", buffer.getvalue())
        with Image.open(to_shape(clear, PORTRAIT)) as shaped:
            assert shaped.getpixel((10, 10)) == (255, 255, 255)


class TestTheFile:
    def test_the_result_is_jpeg_under_the_old_name(self):
        shaped = to_shape(upload_of(500, 500, name="vesna.png"), PORTRAIT)
        assert shaped.name == "vesna.jpg"
        with Image.open(shaped) as image:
            assert image.format == "JPEG"
