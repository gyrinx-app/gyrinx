"""Tests for the supporter badge registry, eligibility logic, and render tag."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.utils import IntegrityError
from django.urls import reverse

from gyrinx.accounts.models import Badge, BadgeGrant, PatreonStatus, UserProfile
from gyrinx.badges import (
    ALL_BADGES,
    HIDE_BADGE,
    PATREON_BADGES,
    STAFF_BADGE,
    badge_by_slug,
    badge_choices,
    invalidate_granted_badges,
    rank_for_tier_title,
)
from gyrinx.site.templatetags.badge_tags import badge_icon, user_badge

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


@pytest.mark.django_db
def test_badge_by_slug():
    # Needs the database: a slug that names no built-in badge is looked for
    # among the granted ones before the answer is "no such badge".
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


@pytest.mark.django_db
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


# --- Granted badges (Badge / BadgeGrant) ---
#
# The badge table is cached per process, and these tests rewrite it constantly.
# Production tolerates a stale entry for the timeout; a test cannot, so each one
# clears it.


@pytest.fixture
def clear_badge_cache():
    invalidate_granted_badges()
    yield
    invalidate_granted_badges()


def _badge(slug="playtester", **kwargs):
    defaults = {
        "title": slug.title(),
        "description": f"The {slug} badge",
    }
    badge = Badge.objects.create(slug=slug, **{**defaults, **kwargs})
    invalidate_granted_badges()
    return badge


def _reloaded(profile):
    """A fresh profile: ``display_badge`` is cached on the instance."""
    return UserProfile.objects.get(pk=profile.pk)


@pytest.mark.django_db
def test_a_granted_badge_becomes_available(user, clear_badge_cache):
    profile = _profile(user)
    badge = _badge()
    BadgeGrant.objects.create(badge=badge, user=user)
    assert profile.eligible_badge_slugs == {"playtester"}


@pytest.mark.django_db
def test_a_badge_nobody_granted_is_not_available(user, clear_badge_cache):
    profile = _profile(user)
    _badge()
    assert profile.eligible_badge_slugs == set()


@pytest.mark.django_db
def test_revoking_a_grant_takes_the_badge_away(user, clear_badge_cache):
    profile = _profile(user, selected_badge="playtester")
    badge = _badge(auto_display=True)
    grant = BadgeGrant.objects.create(badge=badge, user=user)
    assert profile.display_badge.slug == "playtester"

    grant.delete()
    invalidate_granted_badges()
    assert _reloaded(profile).display_badge is None


@pytest.mark.django_db
def test_archiving_a_badge_takes_it_away_from_everyone(user, clear_badge_cache):
    profile = _profile(user)
    badge = _badge(auto_display=True)
    BadgeGrant.objects.create(badge=badge, user=user)

    badge.archived = True
    badge.save()
    invalidate_granted_badges()
    assert _reloaded(profile).display_badge is None


@pytest.mark.django_db
def test_a_grant_to_everyone_reaches_someone_with_no_grant_of_their_own(
    user, clear_badge_cache
):
    profile = _profile(user)
    badge = _badge()
    BadgeGrant.objects.create(badge=badge, audience=BadgeGrant.Audience.EVERYONE)
    assert profile.eligible_badge_slugs == {"playtester"}


@pytest.mark.django_db
def test_a_grant_to_everyone_changes_nobodys_displayed_badge(user, clear_badge_cache):
    """The whole reason auto_display defaults off: granting widely is safe."""
    profile = _profile(user)
    badge = _badge(auto_display=False)
    BadgeGrant.objects.create(badge=badge, audience=BadgeGrant.Audience.EVERYONE)

    assert badge.slug in profile.eligible_badge_slugs
    assert profile.display_badge is None
    assert user_badge(user) == ""


@pytest.mark.django_db
def test_an_opt_in_badge_still_shows_once_it_is_picked(user, clear_badge_cache):
    profile = _profile(user, selected_badge="playtester")
    badge = _badge(auto_display=False)
    BadgeGrant.objects.create(badge=badge, user=user)
    assert profile.display_badge.slug == "playtester"


@pytest.mark.django_db
def test_a_supporter_who_is_also_granted_a_badge_keeps_showing_the_tier(
    user, clear_badge_cache
):
    """Rank decides the default, and a granted badge ranks below the tiers."""
    profile = _profile(
        user, patreon_status=PatreonStatus.ACTIVE, patreon_tier="Guilder"
    )
    badge = _badge(auto_display=True)
    BadgeGrant.objects.create(badge=badge, user=user)

    assert profile.eligible_badge_slugs == {"scummer", "guilder", "playtester"}
    assert profile.display_badge.slug == "guilder"


@pytest.mark.django_db
def test_a_badge_may_not_take_a_built_in_slug(clear_badge_cache):
    """The two kinds share a namespace, because a profile stores a bare slug."""
    with pytest.raises(ValidationError) as refusal:
        Badge(slug="staff", title="Staff", description="Not this one").full_clean()
    assert "slug" in refusal.value.message_dict


@pytest.mark.django_db
def test_a_grant_to_everyone_names_nobody(clear_badge_cache, make_user):
    badge = _badge()
    with pytest.raises(ValidationError):
        BadgeGrant(
            badge=badge,
            audience=BadgeGrant.Audience.EVERYONE,
            user=make_user("somebody", "password"),
        ).full_clean()


@pytest.mark.django_db
def test_a_grant_to_one_person_names_them(clear_badge_cache):
    badge = _badge()
    with pytest.raises(ValidationError):
        BadgeGrant(badge=badge, audience=BadgeGrant.Audience.USER).full_clean()


@pytest.mark.django_db
def test_the_same_person_cannot_be_granted_one_badge_twice(user, clear_badge_cache):
    badge = _badge()
    BadgeGrant.objects.create(badge=badge, user=user)
    with pytest.raises(IntegrityError):
        BadgeGrant.objects.create(badge=badge, user=user)


@pytest.mark.django_db
def test_a_badge_can_only_be_granted_to_everyone_once(clear_badge_cache):
    badge = _badge()
    BadgeGrant.objects.create(badge=badge, audience=BadgeGrant.Audience.EVERYONE)
    with pytest.raises(IntegrityError):
        BadgeGrant.objects.create(badge=badge, audience=BadgeGrant.Audience.EVERYONE)


# --- Uploaded artwork ---


def _stored(markup):
    """Put markup in the site's storage and return its address."""
    name = default_storage.save("badges/test.svg", ContentFile(markup.encode()))
    return default_storage.url(name)


@pytest.mark.django_db
def test_uploaded_artwork_keeps_its_colours(user, clear_badge_cache):
    """A badge is identity artwork, so it is not flattened to the text colour."""
    address = _stored(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" '
        'shape-rendering="crispEdges">'
        '<rect width="2" height="2" fill="#B1873F"/></svg>'
    )
    badge = _badge(artwork_url=address, auto_display=True)
    BadgeGrant.objects.create(badge=badge, user=user)
    _profile(user)

    html = user_badge(user)
    assert "#B1873F" in html
    assert 'shape-rendering="crispEdges"' in html


@pytest.mark.django_db
def test_uploaded_artwork_cannot_carry_script_into_a_page(user, clear_badge_cache):
    """Uploaded artwork is untrusted however staff-only the upload form was."""
    address = _stored(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2">'
        "<script>steal()</script>"
        "<foreignObject><b>hello</b></foreignObject>"
        '<rect width="2" height="2" fill="#abc" onclick="steal()"/></svg>'
    )
    badge = _badge(artwork_url=address, auto_display=True)
    BadgeGrant.objects.create(badge=badge, user=user)
    _profile(user)

    html = user_badge(user)
    assert "<script" not in html.lower()
    assert "onclick" not in html.lower()
    assert "foreignobject" not in html.lower()
    assert 'fill="#abc"' in html


@pytest.mark.django_db
def test_a_badge_with_no_artwork_draws_nothing_at_all(user, clear_badge_cache):
    """No artwork means no markup — not an empty span holding space."""
    badge = _badge(auto_display=True)
    BadgeGrant.objects.create(badge=badge, user=user)
    _profile(user)
    assert user_badge(user) == ""


# --- What drawing a badge per row costs ---


@pytest.mark.django_db
def test_the_gang_index_does_not_query_per_owner(
    client, make_user, make_list, django_assert_max_num_queries, clear_badge_cache
):
    """A badge beside every name must not mean a query for every name.

    The badge tag reads each owner's grants, so without the prefetch on the
    index queryset this grows with the number of distinct owners — the kind of
    regression that is invisible in development and only shows up under load.
    The count is a ceiling rather than an equality so that unrelated work on the
    page does not have to come back and edit this number.
    """
    owners = [make_user(f"owner{n}", "password") for n in range(6)]
    badge = _badge(auto_display=True)
    for owner in owners:
        UserProfile.objects.create(user=owner)
        BadgeGrant.objects.create(badge=badge, user=owner)
        make_list(f"Gang {owner.username}", owner=owner)

    # Warm anything cached per process, so this measures the page and not the
    # first-render cost of the badge table.
    client.get(reverse("core:lists") + "?my=0")

    with django_assert_max_num_queries(20) as captured:
        response = client.get(reverse("core:lists") + "?my=0")

    assert response.status_code == 200
    grant_queries = [
        q for q in captured.captured_queries if "badgegrant" in q["sql"].lower()
    ]
    # One prefetch for the whole page, not one lookup per owner.
    assert len(grant_queries) <= 1, grant_queries
