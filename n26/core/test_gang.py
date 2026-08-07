import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from n26.library.models import GangType
from n26.core.models import Gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


def test_has_the_expected_fields(gang_type, owner):
    gang = Gang.objects.create(
        name="The Bad Girls", owner=owner, gang_type=gang_type, rating=1250, credits=300
    )
    assert (gang.name, gang.rating, gang.credits) == ("The Bad Girls", 1250, 300)
    assert gang.owner == owner
    assert gang.gang_type == gang_type
    assert str(gang) == "The Bad Girls"


def test_rating_and_credits_default_to_zero(gang_type):
    gang = Gang.objects.create(name="Skint", gang_type=gang_type)
    assert (gang.rating, gang.credits) == (0, 0)


@pytest.mark.parametrize("field", ["rating", "credits"])
def test_rejects_negatives(gang_type, field):
    gang = Gang(name="Skint", gang_type=gang_type, **{field: -1})
    with pytest.raises(ValidationError, match=field):
        gang.full_clean()


def test_can_be_archived(gang_type):
    gang = Gang.objects.create(name="Retired", gang_type=gang_type)
    assert gang.archived is False
    gang.archive()
    assert gang.archived is True
    assert gang.archived_at is not None


def test_gang_type_is_protected_from_deletion(gang_type):
    Gang.objects.create(name="The Bad Girls", gang_type=gang_type)
    with pytest.raises(ProtectedError):
        gang_type.delete()


def test_a_gang_type_knows_its_gangs(gang_type):
    Gang.objects.create(name="The Bad Girls", gang_type=gang_type)
    Gang.objects.create(name="The Worse Girls", gang_type=gang_type)
    assert gang_type.gangs.count() == 2


def test_is_not_pack_scoped(gang_type):
    """core is user data — no pack FK, unlike everything in content."""
    assert not hasattr(Gang, "pack")


def test_gang_type_may_come_from_any_pack(homebrew):
    ironhead = GangType.objects.create(name="Ironhead Squats", pack=homebrew)
    gang = Gang.objects.create(name="Prospectors", gang_type=ironhead)
    assert gang.gang_type.pack == homebrew
