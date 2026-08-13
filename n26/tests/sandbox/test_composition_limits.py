"""Composition limits: what a roster should hold at most.

The corrupted-gang rules are written as ranges and as refusals — "0–2
Genestealer Cult Aberrants may be added", "no Fighters with the Brute
Subtype may be added from the gang's list", "Leaders and Champions may be
equipped with up to one Psychic Familiar each". *Notes a limit* says all
three, because nought of something is how a ban is written.

Nothing is refused. The book turns fighters away; we count what is there,
say so when the count is past the limit, and stay quiet otherwise — a gang
inside its allowance should not be told what it is allowed.

Two things get counted, and which one follows the scope. Aimed at the gang
it is a census of the roster, so "0–2 Aberrants" is one note on the gang's
sheet. Aimed at a model it is that model's own rows, which is the whole of
what "each" means in "one Familiar each".
"""

import pytest
from django.contrib.auth.models import User

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_model_card
from n26.tests.sandbox.actions import (
    allows_at_most,
    assign,
    buy,
    create_affiliation,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_subtype,
    create_wargear,
    ef_removes,
    found_gang,
    hire,
    modifier,
    move,
    targets_gang,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: The gang list, and the rank each entry is hired holding. A rank is a
#: built-in fact of the entry, which is what makes it countable.
ENTRIES = [
    ("ganger", "Escher Ganger", 55, "ganger"),
    ("leader", "Escher Queen", 120, "leader"),
    ("aberrant", "Genestealer Cult Aberrant", 90, None),
    ("brute", "Escher Brute", 150, "brute"),
]


@pytest.fixture
def ranks(default_pack):
    """The ranks the corruption's limits speak about."""
    return {
        name.lower(): create_subtype(name)
        for name in ("Leader", "Champion", "Ganger", "Brute")
    }


@pytest.fixture
def familiar(default_pack):
    return create_wargear("Psychic Familiar", price=25)


@pytest.fixture
def corruption(default_pack):
    """One hidden carrier holding everything the corruption says.

    A bundle, the way a house hangs its gang rules off a single thing: the
    limits arrive together and can be cancelled together, which is what
    the retraction case needs.
    """
    return create_hidden("Genestealer Cult Corrupted")


@pytest.fixture
def corrupted(corruption):
    """A gang type founded already corrupted — the carrier is a built-in.

    How a player *picks* a corruption is the affiliation flow's business;
    these limits read the same however their carrier arrived.
    """
    made = create_gang_type("Escher", starting_credits=2000)
    made.built_ins = create_default_set("Escher founding", members=[corruption])
    made.save()
    return made


@pytest.fixture
def profiles(corrupted, ranks, fighter_type):
    made = {}
    for key, name, price, rank in ENTRIES:
        profile = create_profile(name, fighter_type, corrupted, price=price)
        if rank is not None:
            profile.built_ins = create_default_set(
                f"{name} built-ins", members=[ranks[rank]]
            )
            profile.save()
        made[key] = profile
    return made


@pytest.fixture
def gang(corrupted, profiles):
    player = User.objects.create_user("player")
    return found_gang("The Bad Girls", corrupted, owner=player)


def limit_the_roster(carrier, at_most, thing):
    """The census half: a ceiling on what the whole roster holds."""
    return modifier(
        f"Corrupted: at most {at_most} {thing}",
        targets_gang(),
        allows_at_most(at_most, thing),
        carried_by=carrier,
    )


def limit_each(carrier, at_most, thing, ranks):
    """The per-model half: a ceiling on every model of these ranks."""
    return modifier(
        f"Corrupted: {at_most} {thing} each",
        targets_model(with_subtypes=ranks),
        allows_at_most(at_most, thing),
        carried_by=carrier,
    )


def gang_notes(gang):
    """The gang's sheet notes, computed the way every screen computes them."""
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index).notes


def card_for(miniature):
    """One model's card, computed the way every screen computes it."""
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return build_model_card(miniature, card=card, computed=compute(card, index))


def member(gang, name):
    from n26.core.models import Miniature

    return Miniature.objects.get(membership__gang=gang, name=name)


class TestTheGangCensus:
    """The 0–2 in "0–2 Genestealer Cult Aberrants may be added" — counted
    over the roster's entries, said once on the gang's own sheet."""

    def test_a_roster_over_the_limit_is_said(self, gang, profiles, corruption):
        limit_the_roster(corruption, 2, profiles["aberrant"])
        for name in ("Grix", "Skab", "Twitch"):
            hire(gang, profiles["aberrant"], name)

        (note,) = gang_notes(gang)
        assert note.text == (
            "the gang holds 3 Genestealer Cult Aberrant; at most 2 "
            "(Genestealer Cult Corrupted)"
        )
        assert note.about == profiles["aberrant"]

    def test_a_roster_at_the_limit_says_nothing(self, gang, profiles, corruption):
        """Two is allowed, and being allowed is not news."""
        limit_the_roster(corruption, 2, profiles["aberrant"])
        hire(gang, profiles["aberrant"], "Grix")
        hire(gang, profiles["aberrant"], "Skab")

        assert gang_notes(gang) == []

    def test_a_roster_under_the_limit_says_nothing(self, gang, profiles, corruption):
        limit_the_roster(corruption, 2, profiles["aberrant"])
        hire(gang, profiles["aberrant"], "Grix")
        hire(gang, profiles["ganger"], "Yolanda")

        assert gang_notes(gang) == []

    def test_the_gang_sheet_prints_the_note(self, gang, profiles, corruption):
        from n26.core.render_text import gang_to_text

        limit_the_roster(corruption, 2, profiles["aberrant"])
        for name in ("Grix", "Skab", "Twitch"):
            hire(gang, profiles["aberrant"], name)

        text = gang_to_text(gang)
        print("\n" + text)
        assert "holds 3 Genestealer Cult Aberrant; at most 2" in text


class TestABanIsAtMostNought:
    """The "no Fighters with the Brute Subtype may be added from the gang's
    list" clause — the same effect with nothing allowed, so an author never
    has to work out whether they are writing a limit or a ban."""

    def test_one_of_a_banned_rank_is_said_in_the_words_of_a_ban(
        self, gang, profiles, corruption, ranks
    ):
        limit_the_roster(corruption, 0, ranks["brute"])
        hire(gang, profiles["brute"], "Krotch")

        (note,) = gang_notes(gang)
        assert note.text == (
            "the gang holds 1 Brute; none allowed (Genestealer Cult Corrupted)"
        )
        assert note.about == ranks["brute"]

    def test_a_gang_holding_none_of_it_is_never_told(
        self, gang, profiles, corruption, ranks
    ):
        limit_the_roster(corruption, 0, ranks["brute"])
        hire(gang, profiles["ganger"], "Yolanda")

        assert gang_notes(gang) == []


class TestOneEach:
    """The "up to one Psychic Familiar each" clause, which reaches Leaders
    and Champions — a limit on the model, counted over that model's own
    rows and said on its card."""

    def test_a_model_with_two_is_told_on_its_own_card(
        self, gang, profiles, corruption, familiar, ranks
    ):
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        queen = hire(gang, profiles["leader"], "Vesna", paid=120)
        buy(queen, thing=familiar, paid=25)
        buy(queen, thing=familiar, paid=25)

        (remark,) = card_for(queen).remarks
        assert remark.text == (
            "this model holds 2 Psychic Familiar; at most 1 "
            "(Genestealer Cult Corrupted)"
        )
        assert remark.about == familiar
        assert_reconciled(gang)

    def test_a_model_with_one_is_left_alone(
        self, gang, profiles, corruption, familiar, ranks
    ):
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        queen = hire(gang, profiles["leader"], "Vesna", paid=120)
        buy(queen, thing=familiar, paid=25)

        assert card_for(queen).remarks == []
        assert_reconciled(gang)

    def test_each_model_is_counted_alone_and_never_as_a_roster(
        self, gang, profiles, corruption, familiar, ranks
    ):
        """Two Leaders holding one apiece is two allowed models, not a
        roster two over a limit of one — the difference between this and
        the census."""
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        for name in ("Vesna", "Sorrow"):
            queen = hire(gang, profiles["leader"], name, paid=120)
            buy(queen, thing=familiar, paid=25)

        assert gang_notes(gang) == []
        for name in ("Vesna", "Sorrow"):
            assert card_for(member(gang, name)).remarks == []
        assert_reconciled(gang)

    def test_a_model_the_limit_does_not_reach_holds_what_it_likes(
        self, gang, profiles, corruption, familiar, ranks
    ):
        """The scope is Leaders and Champions, so a Ganger is nobody's
        business — and a card outside the rule says nothing."""
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        ganger = hire(gang, profiles["ganger"], "Yolanda", paid=55)
        buy(ganger, thing=familiar, paid=25)
        buy(ganger, thing=familiar, paid=25)

        assert card_for(ganger).remarks == []
        assert_reconciled(gang)

    def test_a_stashed_one_is_nobodys(
        self, gang, profiles, corruption, familiar, ranks
    ):
        """Only what a model holds counts against a per-model limit. A
        familiar in the stash is bought and belongs to no fighter, so the
        Leader carrying one is still carrying one."""
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        queen = hire(gang, profiles["leader"], "Vesna", paid=120)
        buy(queen, thing=familiar, paid=25)
        spare = buy(queen, thing=familiar, paid=25)
        move(spare, to=gang.stash)

        assert card_for(queen).remarks == []
        gang.refresh_from_db()
        gang.stash.refresh_from_db()
        assert_reconciled(gang)


class TestWhatTheGangHoldsIsNotWhatEachModelHolds:
    """The gang's own rows ride every member's card so gang-wide rules can
    reach them. They are the gang's, though, so a count of what a *model*
    holds passes over them — otherwise one familiar bought by the gang
    would put every Leader over their limit at once, and the roster's
    census would read it once per member."""

    def test_a_gang_held_one_is_over_nobodys_limit(
        self, gang, profiles, corruption, familiar, ranks
    ):
        limit_each(corruption, 1, familiar, [ranks["leader"], ranks["champion"]])
        limit_the_roster(corruption, 1, familiar)
        queen = hire(gang, profiles["leader"], "Vesna", paid=120)
        buy(queen, thing=familiar, paid=25)
        assign(familiar, gang=gang, paid=25)

        assert card_for(queen).remarks == []
        assert gang_notes(gang) == []
        assert_reconciled(gang)


class TestARetractedCarriersLimitGoesWithIt:
    """A limit stands only while the thing stating it does. Cancel the
    corruption and the roster stops being over anything — the retraction
    every computed effect gets."""

    @pytest.fixture
    def cure(self, corruption):
        cured = create_affiliation("Purged")
        modifier(
            "Purged: the corruption goes",
            targets_gang(),
            ef_removes(corruption),
            carried_by=cured,
        )
        return cured

    def test_cancelling_the_carrier_takes_the_limit_with_it(
        self, gang, profiles, corruption, cure
    ):
        limit_the_roster(corruption, 2, profiles["aberrant"])
        for name in ("Grix", "Skab", "Twitch"):
            hire(gang, profiles["aberrant"], name)
        assert len(gang_notes(gang)) == 1

        assign(cure, gang=gang)
        assert gang_notes(gang) == []


class TestTheAuthoringSurface:
    """What an author fills in, and what the pickers offer them."""

    def test_the_verb_reads_as_a_sentence(self, default_pack, ranks):
        from n26.library.specs import specs

        effect = specs()["ef_allows_at_most"].compile(
            {"at_most": 2, "thing": ranks["brute"]}
        )
        assert str(effect) == "at most 2 of Brute"

    def test_nought_reads_as_a_ban(self, default_pack, ranks):
        from n26.library.specs import specs

        effect = specs()["ef_allows_at_most"].compile(
            {"at_most": 0, "thing": ranks["brute"]}
        )
        assert str(effect) == "none of Brute"

    def test_the_form_offers_the_three_countable_kinds(self, default_pack):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["ef_allows_at_most"])()
        assert [value for value, _ in form.fields["thing_kind"].choices] == [
            "subtype",
            "profile",
            "wargear",
        ]

    def test_the_composer_offers_it_for_a_model_and_for_the_gang(self, default_pack):
        from n26.library.forms import effect_kind_cards

        (entry,) = [
            card for card in effect_kind_cards() if card["value"] == "ef_allows_at_most"
        ]
        assert entry["label"] == "Notes a limit"
        assert entry["accepts"] == "model gang"

    def test_a_thing_nothing_counts_refuses_in_words(self, default_pack):
        from n26.tests.sandbox.actions import create_rule, ef_allows_at_most

        with pytest.raises(ValueError, match="cannot be counted"):
            ef_allows_at_most(1, create_rule("Cult of Personality"))

    def test_the_composer_saves_a_census_limit(self, client, profiles):
        """The whole authoring flow, as a staff author drives it: the two
        kind pickers, the effect's own two controls, and the row that
        comes out saying what they filled in."""
        from n26.library.models import Modifier

        author = User.objects.create_user("author", is_staff=True)
        client.force_login(author)

        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_gang",
                "effect_kind": "ef_allows_at_most",
                "what-at_most": "2",
                "what-thing_kind": "profile",
                "what-thing_profile": str(profiles["aberrant"].pk),
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
                "conditions-MIN_NUM_FORMS": "0",
                "conditions-MAX_NUM_FORMS": "1000",
            },
        )

        assert response.status_code == 302
        (made,) = Modifier.objects.all()
        assert str(made.effect) == "at most 2 of Genestealer Cult Aberrant"
        assert str(made.scope) == "the gang"
