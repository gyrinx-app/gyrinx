import pytest
from ulid import ULID

from n26.library.models import ContentPack, Profile, get_default_pack

pytestmark = pytest.mark.django_db


class TestULIDPrimaryKey:
    def test_pk_is_a_ulid_and_survives_a_round_trip(self, make_profile):
        profile = make_profile("Alpha")
        assert isinstance(profile.id, ULID)
        assert len(str(profile.id)) == 26
        assert isinstance(Profile.objects.get(pk=profile.pk).id, ULID)

    @pytest.mark.parametrize("form", ["base32", "uuid"])
    def test_lookup_accepts_base32_and_uuid_forms(self, make_profile, form):
        profile = make_profile("Alpha")
        pk = str(profile.id) if form == "base32" else profile.id.to_uuid()
        assert Profile.objects.filter(pk=pk).exists()

    def test_ordering_by_id_is_creation_order(self, make_profile):
        expected = [f"P{i:02d}" for i in range(25)]
        for name in expected:
            make_profile(name)
        assert list(Profile.objects.order_by("id").values_list("name", flat=True)) == (
            expected
        )

    def test_stored_as_a_native_uuid_column(self):
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "select data_type from information_schema.columns "
                "where table_name = 'library_profile' and column_name = 'id'"
            )
            assert cursor.fetchone()[0] == "uuid"


class TestDefaultPack:
    def test_content_lands_in_the_default_pack(self, make_profile):
        assert make_profile("Alpha").pack.slug == "n26"

    def test_default_pack_is_created_on_demand_and_reused(self):
        assert get_default_pack().pk == get_default_pack().pk
        assert ContentPack.objects.filter(slug="n26").count() == 1


class TestPackScoping:
    """The default manager filters nothing — narrowing is always opt-in."""

    @pytest.fixture(autouse=True)
    def content(self, make_profile, homebrew, other_pack):
        self.homebrew = homebrew
        self.other = other_pack
        self.base = make_profile("Base")
        self.brew = make_profile("Brew", pack=homebrew)
        self.far = make_profile("Far", pack=other_pack)

    def test_default_manager_returns_every_pack(self, names):
        assert names(Profile.objects.all()) == ["Base", "Brew", "Far"]

    def test_default_manager_returns_archived_content(self, names):
        self.brew.archive()
        assert "Brew" in names(Profile.objects.all())

    def test_archiving_a_pack_does_not_hide_its_content(self, names):
        """gyrinx#1742: a pack-owner soft delete must not retract content."""
        self.homebrew.archive()
        assert "Brew" in names(Profile.objects.all())

    def test_in_packs_narrows(self, names):
        assert names(Profile.objects.in_packs([self.homebrew])) == ["Brew"]

    def test_in_default_pack_narrows(self, names):
        assert names(Profile.objects.in_default_pack()) == ["Base"]

    def test_selectable_is_default_pack_plus_subscriptions(self, names):
        assert names(Profile.objects.selectable([self.homebrew])) == ["Base", "Brew"]

    def test_selectable_excludes_archived_content_and_packs(self, names):
        self.base.archive()
        self.other.archive()
        selectable = Profile.objects.selectable([self.homebrew, self.other])
        assert names(selectable) == ["Brew"]

    def test_pack_scoping_is_a_plain_indexed_filter(self):
        """No EXISTS anti-join against a side table — just WHERE pack_id IN."""
        sql = str(Profile.objects.in_packs([self.homebrew]).query)
        assert "pack_id" in sql
        assert "EXISTS" not in sql.upper()

    def test_pack_is_protected_from_deletion(self):
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            self.homebrew.delete()


class TestArchived:
    def test_archive_and_unarchive_set_the_timestamp(self, make_profile):
        profile = make_profile("Alpha")
        profile.archive()
        assert profile.archived
        assert profile.archived_at is not None
        profile.unarchive()
        assert not profile.archived
        assert profile.archived_at is None

    def test_archive_cascades_to_archive_with(self, make_profile):
        parent = make_profile("Parent")
        child = make_profile("Child")
        parent.archive_with = [child]
        parent.archive()
        child.refresh_from_db()
        assert child.archived
