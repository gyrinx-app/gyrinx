"""Tests for the supporter badge registry, eligibility logic, and render tag."""

import pytest

from gyrinx.core.badges import (
    ALL_BADGES,
    HIDE_BADGE,
    PATREON_BADGES,
    STAFF_BADGE,
    badge_by_slug,
    badge_choices,
    rank_for_tier_title,
)
from gyrinx.core.models.auth import PatreonStatus, UserProfile
from gyrinx.core.templatetags.badge_tags import badge_icon, user_badge


# --- Registry (pure) ---


def test_patreon_tiers_ranked_scummer_guilder_uphiver():
    ranks = {b.slug: b.rank for b in PATREON_BADGES}
    assert ranks["scummer"] < ranks["guilder"] < ranks["uphiver"]


def test_slugs_are_unique():
    slugs = [b.slug for b in ALL_BADGES]
    assert len(slugs) == len(set(slugs))


def test_staff_badge_registered_and_outranks_patreon_tiers():
    assert STAFF_BADGE in ALL_BADGES
    assert badge_by_slug("staff").title == "Staff"
    # Staff outranks every Patreon tier so it's the default for staff members.
    assert STAFF_BADGE.rank > max(b.rank for b in PATREON_BADGES)


def test_staff_rank_not_in_patreon_tier_machinery():
    # Staff isn't a Patreon tier, so its title must not map to a tier rank.
    assert rank_for_tier_title("Staff") == 0


def test_rank_for_tier_title_maps_known_tiers():
    assert rank_for_tier_title("Scummer") == 1
    assert rank_for_tier_title("Guilder") == 2
    assert rank_for_tier_title("Uphiver") == 3


def test_rank_for_tier_title_is_case_and_space_insensitive():
    assert rank_for_tier_title("  scummer ") == 1
    assert rank_for_tier_title("UPHIVER") == 3


def test_rank_for_tier_title_zero_for_free_empty_and_unknown():
    assert rank_for_tier_title("Free") == 0
    assert rank_for_tier_title("") == 0
    assert rank_for_tier_title("Nonsense") == 0


def test_badge_choices_appends_hide_option():
    choices = badge_choices(PATREON_BADGES)
    assert ("scummer", "Scummer") in choices
    assert choices[-1] == (HIDE_BADGE, "Hide badge")
    # No empty "no badge" option — patrons show their tier badge by default.
    assert ("", "No badge") not in choices


def test_badge_by_slug():
    assert badge_by_slug("guilder").title == "Guilder"
    assert badge_by_slug("") is None
    assert badge_by_slug("nope") is None


# --- Eligibility (UserProfile) ---


def _profile(user, **kwargs):
    return UserProfile.objects.create(user=user, **kwargs)


@pytest.mark.django_db
def test_active_scummer_unlocks_only_scummer(user):
    profile = _profile(
        user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Scummer"
    )
    assert profile.current_tier_rank == 1
    assert [b.slug for b in profile.unlocked_badges] == ["scummer"]
    assert profile.eligible_badge_slugs == {"scummer"}


@pytest.mark.django_db
def test_active_uphiver_unlocks_all(user):
    profile = _profile(
        user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Uphiver"
    )
    assert profile.eligible_badge_slugs == {"scummer", "guilder", "uphiver"}


@pytest.mark.django_db
def test_active_free_tier_unlocks_nothing(user):
    profile = _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Free")
    assert profile.current_tier_rank == 0
    assert profile.unlocked_badges == []


@pytest.mark.django_db
@pytest.mark.parametrize("status", [PatreonStatus.FORMER, PatreonStatus.DECLINED, ""])
def test_non_active_status_unlocks_nothing_even_with_stale_tier(user, status):
    # A lapsed supporter can carry a stale tier; status gating must win.
    profile = _profile(
        user,
        patreon_status=status,
        patreon_tier="Uphiver",
        selected_badge="uphiver",
    )
    assert profile.current_tier_rank == 0
    assert profile.unlocked_badges == []
    assert profile.display_badge is None


@pytest.mark.django_db
def test_display_badge_returns_selected_when_eligible(user):
    profile = _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Uphiver",
        selected_badge="guilder",
    )
    assert profile.display_badge is not None
    assert profile.display_badge.slug == "guilder"


@pytest.mark.django_db
def test_display_badge_falls_back_to_current_tier_when_selection_above_tier(user):
    # A stale selection above the user's current tier (e.g. after a downgrade)
    # isn't shown; they fall back to their current-tier badge rather than nothing.
    profile = _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Scummer",
        selected_badge="uphiver",
    )
    assert profile.display_badge.slug == "scummer"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tier,expected",
    [("Scummer", "scummer"), ("Guilder", "guilder"), ("Uphiver", "uphiver")],
)
def test_display_badge_defaults_to_current_tier_when_no_selection(user, tier, expected):
    # The headline behaviour: active patrons show their tier badge with no choice.
    profile = _profile(user, patreon_status=PatreonStatus.ACTIVE, patreon_tier=tier)
    assert profile.display_badge.slug == expected


@pytest.mark.django_db
def test_display_badge_hidden_with_opt_out(user):
    profile = _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Uphiver",
        selected_badge=HIDE_BADGE,
    )
    assert profile.display_badge is None


# --- Staff badge eligibility ---


@pytest.mark.django_db
def test_staff_user_shows_staff_badge_by_default(user):
    user.is_staff = True
    user.save()
    profile = _profile(user)
    assert [b.slug for b in profile.available_badges] == ["staff"]
    assert profile.eligible_badge_slugs == {"staff"}
    # Opt-out semantics: shown by default with no explicit choice.
    assert profile.display_badge.slug == "staff"


@pytest.mark.django_db
def test_non_staff_user_has_no_staff_badge(user):
    profile = _profile(user)
    assert profile.available_badges == []
    assert profile.display_badge is None


@pytest.mark.django_db
def test_staff_plus_patreon_defaults_to_staff(user):
    user.is_staff = True
    user.save()
    profile = _profile(
        user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Uphiver"
    )
    assert profile.eligible_badge_slugs == {"scummer", "guilder", "uphiver", "staff"}
    # Staff outranks the tiers, so it wins the no-selection default.
    assert profile.display_badge.slug == "staff"


@pytest.mark.django_db
def test_staff_user_can_select_a_patreon_badge(user):
    user.is_staff = True
    user.save()
    profile = _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    assert profile.display_badge.slug == "guilder"


@pytest.mark.django_db
def test_staff_user_can_hide_badge(user):
    user.is_staff = True
    user.save()
    profile = _profile(user, selected_badge=HIDE_BADGE)
    assert profile.display_badge is None


@pytest.mark.django_db
def test_losing_staff_retracts_staff_badge(user):
    # A stored "staff" selection self-heals once staff access is removed.
    profile = _profile(user, selected_badge="staff")  # user.is_staff is False
    assert profile.available_badges == []
    assert profile.display_badge is None


# --- Template tags ---


def test_badge_icon_renders_inline_svg():
    html = badge_icon("scummer")
    assert "<svg" in html
    assert "currentColor" in html
    assert 'aria-label="Scummer"' in html


def test_badge_icon_empty_for_unknown():
    assert badge_icon("nope") == ""
    assert badge_icon("") == ""


@pytest.mark.django_db
def test_user_badge_renders_for_eligible_user(user):
    _profile(
        user,
        patreon_status=PatreonStatus.ACTIVE,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    html = user_badge(user)
    assert "<svg" in html
    assert 'data-bs-toggle="tooltip"' in html
    assert 'data-bs-title="Gyrinx supporter — Guilder tier"' in html
    assert 'aria-label="Gyrinx supporter — Guilder tier"' in html


@pytest.mark.django_db
def test_user_badge_renders_staff_badge(user):
    user.is_staff = True
    user.save()
    _profile(user)
    html = user_badge(user)
    assert "<svg" in html
    assert 'data-bs-title="Gyrinx staff"' in html
    assert 'aria-label="Gyrinx staff"' in html


@pytest.mark.django_db
def test_user_badge_empty_for_ineligible_user(user):
    _profile(
        user,
        patreon_status=PatreonStatus.FORMER,
        patreon_tier="Guilder",
        selected_badge="guilder",
    )
    assert user_badge(user) == ""


@pytest.mark.django_db
def test_user_badge_empty_without_profile(user):
    assert user_badge(user) == ""


def test_user_badge_empty_for_none():
    assert user_badge(None) == ""
