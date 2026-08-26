import pytest
from django.contrib.auth.models import User

from n26.core.models import Assignment, Gang, Miniature

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, owner):
    return Gang.objects.create(name="The Bad Girls", gang_type=gang_type, owner=owner)


@pytest.fixture
def profile_assignable(make_profile):
    return make_profile("Escher Juve")


def test_has_a_name_and_an_owner(owner):
    mini = Miniature.objects.create(name="Yolanda", owner=owner)
    assert mini.name == "Yolanda"
    assert mini.owner == owner
    assert str(mini) == "Yolanda"


def test_is_labelled_model_in_the_ui():
    assert Miniature._meta.verbose_name == "model"
    assert Miniature._meta.verbose_name_plural == "models"


def test_has_no_profile_field_yet():
    """The profile arrives via the membership assignment, not a direct field."""
    assert not hasattr(Miniature, "profile")


def test_membership_puts_a_model_in_a_gang(gang, owner, profile_assignable):
    mini = Miniature.objects.create(name="Yolanda", owner=owner)
    membership = Assignment.objects.create(assignable=profile_assignable, gang=gang)
    mini.membership = membership
    mini.save()

    assert mini.gang == gang
    assert membership.member == mini
    assert list(gang.hosted_assignments.all()) == [membership]


def test_a_model_without_a_membership_has_no_gang(owner):
    assert Miniature.objects.create(name="Spare", owner=owner).gang is None


def test_a_gang_holds_many_models(gang, owner, profile_assignable):
    for name in ["Yolanda", "Mad Donna"]:
        mini = Miniature.objects.create(name=name, owner=owner)
        mini.membership = Assignment.objects.create(
            assignable=profile_assignable, gang=gang
        )
        mini.save()

    assert sorted(a.member.name for a in gang.hosted_assignments.all()) == [
        "Mad Donna",
        "Yolanda",
    ]


def test_deleting_a_gang_takes_its_models_with_it(gang, owner, profile_assignable):
    """Every route to a model goes through its gang, so a model left
    behind is a row nothing can show, edit or delete. A model standing
    on its own is a feature the design considered and dropped, so the
    gang takes its models with it."""
    mini = Miniature.objects.create(name="Yolanda", owner=owner)
    mini.membership = Assignment.objects.create(
        assignable=profile_assignable, gang=gang
    )
    mini.save()

    gang.delete()

    assert Assignment.objects.count() == 0
    assert not Miniature.objects.filter(pk=mini.pk).exists()


def test_a_model_with_no_membership_yet_survives_a_gang_going(
    gang, owner, profile_assignable
):
    """The cascade runs off the membership, so a model written before one
    is attached — the order ``Operations.hire`` writes in — is not swept
    up by an unrelated gang being deleted."""
    unattached = Miniature.objects.create(name="Yolanda", owner=owner)

    gang.delete()

    assert Miniature.objects.filter(pk=unattached.pk).exists()
