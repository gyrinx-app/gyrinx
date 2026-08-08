"""Where a gang type's badge is allowed to come from.

The badge is drawn inline, so the server reads the bytes at whatever address
the row holds. That makes the address a security boundary rather than a
convenience: these pin that only this site's own storage resolves, that
everything else draws nothing, and that neither an upload nor a paste can make
the server go and fetch something.
"""

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from n26.library import artwork
from n26.library.admin import GangTypeForm
from n26.library.forms import generate_form
from n26.library.models import GangType
from n26.library.specs import specs

pytestmark = pytest.mark.django_db

SOURCE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
    '<path d="M2 2h8v8H2Z"/></svg>'
)


@pytest.fixture(autouse=True)
def clean_artwork_cache():
    """Read artwork is cached against the object it came from, and the
    cache outlives a test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def upload(source=SOURCE, name="badge.svg"):
    return SimpleUploadedFile(name, source.encode(), content_type="image/svg+xml")


class TestWhichAddressesResolve:
    """An address names an object in this site's storage, or it names
    nothing at all. There is no third answer, and no address makes the
    server fetch anything."""

    def test_an_address_in_the_sites_own_storage_names_its_object(self, own_storage):
        assert artwork.storage_key("/media/gang-type-icons/x.svg") == (
            "gang-type-icons/x.svg"
        )

    @pytest.mark.parametrize(
        "address",
        [
            "https://evil.example/badge.svg",
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8000/media/x.svg",
            "file:///etc/passwd",
            "//evil.example/media/x.svg",
        ],
    )
    def test_an_address_somewhere_else_names_nothing(self, own_storage, address):
        """Nothing here is fetched — an address outside the storage
        simply does not resolve, so there is no request to make."""
        assert artwork.storage_key(address) is None

    def test_climbing_out_of_the_storage_names_nothing(self, own_storage):
        assert artwork.storage_key("/media/../../etc/passwd") is None

    def test_climbing_out_in_disguise_names_nothing(self, own_storage):
        """Percent-encoding is decoded before the check, not after."""
        assert artwork.storage_key("/media/%2e%2e/%2e%2e/etc/passwd") is None

    def test_a_hostname_that_merely_starts_the_same_names_nothing(
        self, settings, own_storage
    ):
        settings.GS_BUCKET_NAME = "uploads"
        assert (
            artwork.storage_key("https://storage.googleapis.com/uploads.evil/x.svg")
            is None
        )

    def test_the_bucket_answers_as_well_as_whatever_publishes_it(
        self, settings, own_storage
    ):
        """A CDN in front of the bucket does not stop the bucket serving
        the same object, and both addresses are ones an author has."""
        settings.GS_BUCKET_NAME = "uploads"
        assert artwork.storage_key(
            "https://storage.googleapis.com/uploads/gang-type-icons/x.svg"
        ) == ("gang-type-icons/x.svg")

    def test_a_trailing_query_names_the_same_object(self, own_storage):
        assert artwork.storage_key("/media/gang-type-icons/x.svg?v=2") == (
            "gang-type-icons/x.svg"
        )

    def test_nothing_at_all_names_nothing(self, own_storage):
        assert artwork.storage_key("") is None
        assert artwork.storage_key(None) is None


class TestReadingWhatAnAddressNames:
    def test_a_stored_drawing_comes_back_as_source(self, store_artwork):
        assert artwork.read(store_artwork(SOURCE)) == SOURCE

    def test_an_address_naming_nothing_reads_as_nothing(self, own_storage):
        assert artwork.read("https://evil.example/badge.svg") == ""

    def test_a_missing_object_reads_as_nothing(self, own_storage):
        """Storage failing is not a reason for a page to stop drawing."""
        assert artwork.read("/media/gang-type-icons/gone.svg") == ""

    def test_something_far_too_large_to_be_a_badge_reads_as_nothing(
        self, store_artwork
    ):
        address = store_artwork("<svg>" + "x" * artwork.MAX_BYTES, "huge.svg")
        assert artwork.read(address) == ""

    def test_a_second_read_does_not_go_back_to_storage(
        self, store_artwork, own_storage
    ):
        address = store_artwork(SOURCE)
        assert artwork.read(address) == SOURCE
        (own_storage / "gang-type-icons" / "badge.svg").unlink()
        assert artwork.read(address) == SOURCE


class TestWhatAGangTypeSays:
    """One accessor, so no surface has to know an address is involved."""

    def test_a_type_with_no_badge_says_nothing(self, default_pack):
        assert GangType.objects.create(name="Plain").artwork == ""

    def test_a_type_with_a_badge_says_its_source(self, default_pack, store_artwork):
        gang_type = GangType.objects.create(
            name="Drawn", icon_url=store_artwork(SOURCE)
        )
        assert gang_type.artwork == SOURCE

    def test_a_type_pointed_somewhere_else_says_nothing(
        self, default_pack, own_storage
    ):
        gang_type = GangType.objects.create(
            name="Elsewhere", icon_url="https://evil.example/badge.svg"
        )
        assert gang_type.artwork == ""


class TestUploading:
    def test_a_drawing_is_stored_and_its_address_resolves(self, own_storage):
        address = artwork.store(upload())
        assert artwork.storage_key(address) is not None
        assert artwork.read(address) == SOURCE

    def test_it_lands_where_badges_live(self, own_storage):
        assert artwork.UPLOAD_PREFIX in artwork.store(upload())

    def test_something_that_is_not_an_svg_file_is_refused(self, own_storage):
        with pytest.raises(ValidationError):
            artwork.store(upload(name="badge.png"))

    def test_a_file_with_no_svg_in_it_is_refused(self, own_storage):
        with pytest.raises(ValidationError):
            artwork.store(upload("<html><body>hello</body></html>"))

    def test_a_file_too_large_to_be_a_badge_is_refused(self, own_storage):
        with pytest.raises(ValidationError):
            artwork.store(upload("<svg>" + "x" * artwork.MAX_BYTES))


class TestTheAuthoringForm:
    """Two controls, one value. An author uploads a drawing or gives an
    address; only the address is stored."""

    @pytest.fixture
    def form_class(self):
        return generate_form(specs()["create_gang_type"])

    def test_an_upload_becomes_the_address(self, form_class, own_storage, default_pack):
        form = form_class({"name": "Goliath"}, {"icon_url_upload": upload()})
        assert form.is_valid(), form.errors
        created = form.compile()
        assert created.artwork == SOURCE

    def test_an_upload_replaces_an_address_already_in_the_box(
        self, form_class, own_storage, default_pack, store_artwork
    ):
        """Uploading cannot happen by accident, while the box arrives
        pre-filled — so uploading is how a badge gets replaced."""
        old = store_artwork("<svg viewBox='0 0 1 1'><path d='M0 0'/></svg>", "old.svg")
        form = form_class(
            {"name": "Goliath", "icon_url": old}, {"icon_url_upload": upload()}
        )
        assert form.is_valid(), form.errors
        assert form.compile().artwork == SOURCE

    def test_an_address_outside_the_storage_is_refused_in_words(
        self, form_class, own_storage, default_pack
    ):
        form = form_class({"name": "Goliath", "icon_url": "https://evil.example/x.svg"})
        assert not form.is_valid()
        assert artwork.NOT_OURS in form.errors["icon_url"]

    def test_a_pasted_address_in_the_storage_is_kept(
        self, form_class, own_storage, default_pack, store_artwork
    ):
        address = store_artwork(SOURCE)
        form = form_class({"name": "Goliath", "icon_url": address})
        assert form.is_valid(), form.errors
        assert form.compile().icon_url == address

    def test_no_badge_at_all_is_fine(self, form_class, own_storage, default_pack):
        form = form_class({"name": "Goliath"})
        assert form.is_valid(), form.errors
        assert form.compile().icon_url == ""

    def test_editing_reads_the_address_back_into_the_box(
        self, form_class, own_storage, default_pack, store_artwork
    ):
        address = store_artwork(SOURCE)
        gang_type = GangType.objects.create(name="Goliath", icon_url=address)
        assert form_class.opened_on(gang_type).initial["icon_url"] == address

    def test_editing_can_clear_a_badge(
        self, form_class, own_storage, default_pack, store_artwork
    ):
        gang_type = GangType.objects.create(
            name="Goliath", icon_url=store_artwork(SOURCE)
        )
        form = form_class.opened_on(
            gang_type, {"edit-name": "Goliath", "edit-icon_url": ""}
        )
        assert form.is_valid(), form.errors
        form.apply_to(gang_type)
        gang_type.refresh_from_db()
        assert gang_type.icon_url == ""


class TestTheAuthoringPage:
    """Both controls are drawn, and the form is told it carries a file —
    without that the browser posts the file's name and nothing else."""

    @pytest.fixture
    def author(self, db):
        return User.objects.create_user("author", is_staff=True)

    def test_the_create_page_offers_both_ways_in(self, client, author, default_pack):
        client.force_login(author)
        body = client.get("/n26/authoring/gang-type/new/").content.decode()

        assert 'name="icon_url"' in body
        assert 'name="icon_url_upload"' in body
        assert 'enctype="multipart/form-data"' in body

    def test_uploading_through_the_page_stores_the_drawing(
        self, client, author, own_storage, default_pack
    ):
        client.force_login(author)
        client.post(
            "/n26/authoring/gang-type/new/",
            {"name": "Goliath", "icon_url": "", "icon_url_upload": upload()},
        )
        assert GangType.objects.get(name="Goliath").artwork == SOURCE


class TestTheAdmin:
    """The admin is the other surface an author edits content from, so it
    offers the same pair rather than a bare address box."""

    def _payload(self, default_pack, **extra):
        return {
            "pack": str(default_pack.pk),
            "name": "Goliath",
            "price": "0",
            "position": "0",
            **extra,
        }

    def test_the_add_page_offers_both_ways_in(self, admin_client, default_pack):
        body = admin_client.get("/admin/library/gangtype/add/").content.decode()
        assert 'name="icon_url"' in body
        assert 'name="icon_url_upload"' in body

    def test_an_upload_becomes_the_address(
        self, admin_client, own_storage, default_pack
    ):
        form = GangTypeForm(self._payload(default_pack), {"icon_url_upload": upload()})
        assert form.is_valid(), form.errors
        assert form.save().artwork == SOURCE

    def test_an_address_outside_the_storage_is_refused_in_words(
        self, admin_client, own_storage, default_pack
    ):
        form = GangTypeForm(
            self._payload(default_pack, icon_url="https://evil.example/x.svg")
        )
        assert not form.is_valid()
        assert artwork.NOT_OURS in form.errors["icon_url"]
