"""Making choices through the screens.

The engine underneath is pinned elsewhere — ``test_outcast_gang.py`` for
archetypes and affiliations, ``test_venator_skill_trees.py`` for the
whole-kind pick, ``test_specialist.py`` for the ordinary one. This file
is about the surface: that an open slot draws as something to
click, that clicking it lists what *this* card may pick, and that the
click writes a row the slot then reads back.

The three questions here are deliberately unalike underneath — a skill
narrowed to a tier the archetype opens, an archetype whose pick belongs
to the gang, an affiliation the gang itself is asked — and the screens
tell them apart by nothing at all. One route, one page, one click.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.models import Assignment, DismissedOffer
from n26.core.reconcile import assert_reconciled
from n26.core.render import NONE_KEY, build_choice_offer, render_gang
from n26.library.models import Affiliation, Skill
from n26.tests.sandbox.actions import (
    add_entry,
    adds,
    choose,
    create_affiliation,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_power,
    create_profile,
    create_skill,
    create_subtype,
    found_gang,
    has_subtypes,
    hire,
    hire_with_option,
    modifier,
    offers_choice,
    places,
    remove,
    section_of,
    targets_every_model,
    targets_gang,
    targets_model,
)

pytestmark = [pytest.mark.django_db, pytest.mark.core]


# --- A gang list small enough to read, wide enough to cover the shapes ----


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def sets(default_pack):
    return {
        name.lower(): create_category("Skills", name, position)
        for position, name in enumerate(["Combat", "Shooting"])
    }


@pytest.fixture
def skills(sets):
    return {
        name: create_skill(name, category=sets[key])
        for key, name in [
            ("combat", "Berserker"),
            ("combat", "Parry"),
            ("shooting", "Marksman"),
        ]
    }


@pytest.fixture
def skills_collection(skills):
    collection = create_collection(
        "Skills", entries=[(skill, {}) for skill in skills.values()]
    )
    return collection, {
        "primary": section_of(collection, "Primary", 0),
        "other": section_of(collection, "Other", 1, is_default=True),
    }


@pytest.fixture
def subtypes(db):
    return {"leader": create_subtype("Leader"), "ganger": create_subtype("Ganger")}


@pytest.fixture
def archetypes(sets, skills_collection, subtypes):
    """Two a gang may take, each opening one skill set as Primary."""
    _, tiers = skills_collection
    made = {}
    for name, set_key in [("Brawler", "combat"), ("Gunslinger", "shooting")]:
        archetype = create_affiliation(name)
        modifier(
            f"{name}: {set_key} is Primary",
            targets_every_model(has_subtypes(subtypes["leader"], subtypes["ganger"])),
            places(sets[set_key], tiers["primary"]),
            carried_by=archetype,
        )
        made[name] = archetype
    return made


@pytest.fixture
def affiliations(db):
    return {
        name: create_affiliation(name) for name in ("Clanless", "Mutant", "Aranthian")
    }


@pytest.fixture
def pick_lists(archetypes, affiliations):
    made = {}
    for key, name, things in [
        ("archetypes", "Archetypes", archetypes.values()),
        ("affiliations", "Affiliations", affiliations.values()),
    ]:
        collection = create_collection(name, entries=[(t, {}) for t in things])
        made[key] = section_of(collection, name, 0, is_default=True)
    return made


@pytest.fixture
def gang_list(subtypes, skills_collection, pick_lists, affiliations):
    """The gang type: the gang's own affiliation question, a whole-kind
    question beside it, and the skill offer every Leader carries."""
    _, tiers = skills_collection
    gang_type = create_gang_type("Outcasts")

    # Two questions on one carrier, which is why an address names the
    # offer as well as the row it hangs off: without it, choosing for one
    # would read as having settled the other.
    #
    # The second names a kind with nothing narrowing it, which is the
    # branch with no collection to browse.
    questions = create_hidden("Gang questions")
    modifier(
        "Outcasts: the gang takes an Affiliation",
        targets_gang(),
        offers_choice(
            Affiliation, from_section=pick_lists["affiliations"], label="affiliation"
        ),
        carried_by=questions,
    )
    modifier(
        "Outcasts: the gang favours one of them outright",
        targets_gang(),
        offers_choice(Affiliation, label="favoured set"),
        carried_by=questions,
    )
    gang_type.built_ins = create_default_set("Outcast built-ins", members=[questions])
    gang_type.save()

    # Carried by the gang type and scoped to Leaders: the slot lands on
    # every Leader's card through the broadcast, and each chosen row names
    # its own fighter.
    modifier(
        "Outcasts: a Leader starts with a Primary skill",
        targets_every_model(has_subtypes(subtypes["leader"])),
        offers_choice(Skill, from_section=tiers["primary"]),
        carried_by=gang_type,
    )
    return gang_type


@pytest.fixture
def profiles(gang_list, subtypes, pick_lists, person_type):
    made = {}
    for key, name in [("leader", "Outcast Leader"), ("ganger", "Outcast Ganger")]:
        profile = create_profile(name, person_type, gang_list, price=0)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[subtypes[key]]
        )
        profile.save()
        made[key] = profile
    # What is chosen is the gang's, though the Leader is asked.
    modifier(
        "Outcast Leader: chooses the gang's Archetype",
        targets_model(),
        offers_choice(
            Affiliation,
            from_section=pick_lists["archetypes"],
            label="archetype",
            will_be_assigned_to="gang",
        ),
        carried_by=made["leader"],
    )
    return made


@pytest.fixture
def whispers(gang_list, subtypes, skills_collection):
    """A family of powers filed in the skills collection, Primary for
    Leaders — what a psychic gang list looks like.

    Powers are not skills, and both sit in one collection under one set
    of tiers: the fighter who browses skills at Primary browses these
    beside them.
    """
    collection, tiers = skills_collection
    family = create_category("Wyrd Powers", "Psychoteric Whispers")
    powers = {
        name: create_power(name, "Double", category=family, position=position)
        for position, name in enumerate(["Mind Lock", "Warp Sight"], start=1)
    }
    for power in powers.values():
        add_entry(collection, power)
    modifier(
        "Outcasts: the whispers are Primary for Leaders",
        targets_every_model(has_subtypes(subtypes["leader"])),
        places(family, tiers["primary"]),
        carried_by=gang_list,
    )
    return powers


@pytest.fixture
def gang(gang_list, owner):
    return found_gang("The Forgotten", gang_list, owner=owner)


@pytest.fixture
def crew(gang, profiles):
    return {
        "leader": hire_with_option(gang, profiles["leader"], "Sorrow"),
        "ganger": hire_with_option(gang, profiles["ganger"], "Rat"),
    }


# --- Reading the slots off the rendered sheet -----------------------------


def sheet_slots(gang):
    """Every slot the gang sheet draws, by label — the gang's own and each
    member's, exactly as the view assembles them.

    A card keeps the questions asking for a skill in a list of their own,
    because it draws them in the Skills row rather than among the others.
    Both lists are read here: where a question is drawn is the card's
    business, and every one of them is a slot with an address."""
    from n26.core.views.choose import link_slots

    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    found = {line.kind_label: line for line in sheet.choices}
    for card in sheet.models:
        for line in card.questions:
            found[f"{card.name}: {line.kind_label}"] = line
    return found


def offer_for(slot_line):
    """The pick screen's structure for one drawn slot, without the view."""
    from n26.core.views.choose import find_slot

    gang = Assignment.objects.get(pk=slot_line.key.split(":")[1]).gang_root
    found = find_slot(gang, slot_line.key)
    return build_choice_offer(found.slot, found.computed)


def names_on(offer):
    return {option.name for group in offer.groups for option in group.options}


def _slot_href(gang, miniature, kind_label):
    """A question's address even once it has been answered.

    A card files an answered skill question into the Skills row rather
    than drawing it again, so the sheet stops listing it — but the
    question is still asked and still has an address, which is what a
    stale page or a second click posts to.
    """
    computed = fighter_computed(miniature)
    slot = next(
        line
        for line in computed.choices
        if line.kind_label == kind_label
        and getattr(line.anchor, "assignment", None) is not None
        and line.identity is not None
    )
    key = f"{miniature.pk}:{slot.anchor.assignment.pk}:{slot.identity.pk}"
    return reverse("n26-choose", args=[gang.pk, key])


def _skills_of(gang, name):
    card = next(c for c in render_gang(gang).models if c.name == name)
    return sorted(line.name for line in card.skills)


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def fighter_computed(miniature):
    card = build_card(miniature)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


class TestAnOpenSlotIsAnInvitation:
    """A slot nobody has chosen for draws as something to click, and
    as nothing else: it is not an error and nothing counts it."""

    def test_every_open_slot_carries_the_address_of_its_own_picker(self, gang, crew):
        slots = sheet_slots(gang)
        assert set(slots) == {
            "Affiliation",
            "Favoured set",
            "Sorrow: Archetype",
            "Sorrow: Primary skill",
        }
        assert not any(line.is_resolved for line in slots.values())
        assert all(line.href for line in slots.values())

    def test_two_slots_on_one_carrier_get_two_addresses(self, gang, crew):
        """Both gang questions ride the same row, so only the offer tells
        them apart."""
        slots = sheet_slots(gang)
        assert slots["Affiliation"].href != slots["Favoured set"].href

    def test_two_cards_asked_the_same_question_get_two_addresses(
        self, gang, crew, profiles
    ):
        hire_with_option(gang, profiles["leader"], "Ash")
        slots = sheet_slots(gang)
        assert slots["Sorrow: Archetype"].href != slots["Ash: Archetype"].href

    def test_the_sheet_says_choose(self, client, owner, gang, crew):
        client.force_login(owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert "Choose" in body
        slots = sheet_slots(gang)
        # The gang's strip and a fighter's card both, each pointing at its
        # own slot rather than at some page-wide picker.
        assert slots["Affiliation"].href in body
        assert slots["Sorrow: Primary skill"].href in body

    def test_a_card_with_no_stored_rows_has_no_address(self, gang_list, profiles):
        """A hire preview has real offers and nothing to choose against,
        so its lines are drawn as facts, not as dead controls."""
        from n26.core.card import build_card_from_profile
        from n26.core.render import card_to_model_card

        card = build_card_from_profile(profiles["leader"])
        index = build_modifier_index([node.assignable for node in card.all_nodes()])
        preview = card_to_model_card(card, compute(card, index), name="Nobody")
        assert preview.questions
        assert all(line.key == "" and line.href == "" for line in preview.questions)


class TestWhatOneCardMayPick:
    """The list is the offer's own, shaped by the card it is offered on."""

    def test_a_narrowed_offer_lists_only_that_tier(self, gang, crew, archetypes):
        """Before the archetype, no set is Primary and the skill slot has
        nothing in it; after it, exactly that archetype's set."""
        slots = sheet_slots(gang)
        assert offer_for(slots["Sorrow: Primary skill"]).is_empty

        choose(gang_anchor(gang, "Outcast Leader", crew), archetypes["Brawler"])
        offer = offer_for(sheet_slots(gang)["Sorrow: Primary skill"])
        assert names_on(offer) == {"Berserker", "Parry"}
        assert [group.name for group in offer.groups] == ["Combat"]

    def test_an_unnarrowed_offer_lists_the_whole_kind(self, gang, crew):
        offer = offer_for(sheet_slots(gang)["Favoured set"])
        assert names_on(offer) == {
            "Clanless",
            "Mutant",
            "Aranthian",
            "Brawler",
            "Gunslinger",
        }
        # Nothing narrows it, so there is nothing to head the list with.
        assert [group.name for group in offer.groups] == [""]

    def test_the_pick_page_draws_the_list(self, client, owner, gang, crew):
        client.force_login(owner)
        body = client.get(sheet_slots(gang)["Affiliation"].href).content.decode()
        for name in ("Clanless", "Mutant", "Aranthian"):
            assert name in body

    def test_an_empty_offer_says_so_rather_than_hiding(self, client, owner, gang, crew):
        client.force_login(owner)
        body = client.get(
            sheet_slots(gang)["Sorrow: Primary skill"].href
        ).content.decode()
        assert "Nothing is available to choose here" in body


class TestATierHoldingTwoKinds:
    """The list is what may be chosen, and only that.

    A tier is not a kind: a Leader whose Primary sets include a family of
    powers browses skills and powers under the one heading, and the
    question they carry asks for a skill. A power drawn beside the skills
    would be a button that cannot work — the slot reads as resolved only
    where what was chosen matches the offer, so a power would leave the
    question open with a stray row beside it.
    """

    def test_a_skill_question_lists_the_skills_and_not_the_powers(
        self, gang, crew, archetypes, whispers
    ):
        choose(gang_anchor(gang, "Outcast Leader", crew), archetypes["Brawler"])
        offer = offer_for(sheet_slots(gang)["Sorrow: Primary skill"])

        assert names_on(offer) == {"Berserker", "Parry"}
        assert [group.name for group in offer.groups] == ["Combat"]

    def test_a_tier_of_nothing_but_powers_offers_nothing(self, gang, crew, whispers):
        """Without the archetype no skill set is Primary, so the whispers
        are all that tier holds — and the question says it has nothing on
        offer rather than drawing clicks that write nothing."""
        assert offer_for(sheet_slots(gang)["Sorrow: Primary skill"]).is_empty

    def test_the_powers_are_still_there_to_browse(
        self, gang, crew, whispers, skills_collection
    ):
        """Nothing is hidden from the fighter. The family really is in
        their Primary tier, so a screen that deals in powers finds it
        there — it is the skill question, and only that, which declines to
        offer them."""
        from n26.core.browse import browse, placements_for, regrouped_by_placement

        collection, _ = skills_collection
        computed = fighter_computed(crew["leader"])
        view = regrouped_by_placement(
            browse(collection),
            placements_for(computed, collection),
            fallback=collection.default_section(),
        )

        primary = next(
            section for section in view.sections if section.name == "Primary"
        )
        assert "Psychoteric Whispers" in [
            category.name for category in primary.categories
        ]


class TestGettingToTheNextFighter:
    """A fighter's question carries the gang's other fighters beside the
    heading; the gang's own questions carry nobody.

    Each row leads to that fighter's equip screen. A slot's address names
    one card's carrier and one offer, so the page being looked at has no
    counterpart for anybody else — the kit screen is the fighter page they
    all have.
    """

    def test_a_fighters_question_offers_the_others(self, client, owner, gang, crew):
        client.force_login(owner)
        body = client.get(sheet_slots(gang)["Sorrow: Archetype"].href).content.decode()

        assert reverse("n26-equip", args=[crew["ganger"].pk]) in body
        assert "Rat" in body

    def test_the_fighter_being_asked_is_marked_as_the_one_you_are_on(
        self, client, owner, gang, crew
    ):
        client.force_login(owner)
        body = client.get(sheet_slots(gang)["Sorrow: Archetype"].href).content.decode()

        theirs = body.index(reverse("n26-equip", args=[crew["leader"].pk]))
        assert 'aria-current="page"' in body[theirs : body.index("</a>", theirs)]

    def test_the_gangs_own_question_offers_nobody(self, client, owner, gang, crew):
        """An affiliation belongs to the gang rather than to anyone on the
        roster, so a list of fighters beside it would offer a switch to
        somewhere this question does not exist."""
        client.force_login(owner)
        body = client.get(sheet_slots(gang)["Affiliation"].href).content.decode()

        for miniature in crew.values():
            assert reverse("n26-equip", args=[miniature.pk]) not in body


def gang_anchor(gang, assignable_name, crew):
    """The stored row whose assignable carries an offer."""
    for miniature in crew.values():
        for row in miniature.assignments.all():
            if str(row.assignable) == assignable_name:
                return row
    return next(
        row for row in gang.assignments.all() if str(row.assignable) == assignable_name
    )


class TestMakingOneChoice:
    """One click writes one row, and the slot reads it back."""

    def post(self, client, href, thing):
        return client.post(href, {"thing": f"{thing._meta.label_lower}:{thing.pk}"})

    def test_the_gangs_own_question(self, client, owner, gang, crew, affiliations):
        client.force_login(owner)
        response = self.post(
            client, sheet_slots(gang)["Affiliation"].href, affiliations["Mutant"]
        )
        assert response.status_code == 302

        chosen = Assignment.objects.get(affiliation=affiliations["Mutant"])
        assert chosen.gang == gang
        assert sheet_slots(gang)["Affiliation"].chosen == "Mutant"
        assert_reconciled(gang)

    def test_one_carriers_other_question_stays_open(
        self, client, owner, gang, crew, affiliations
    ):
        """Both gang questions hang off the same row. Choosing for one
        must not read as having settled the other."""
        client.force_login(owner)
        self.post(client, sheet_slots(gang)["Affiliation"].href, affiliations["Mutant"])
        slots = sheet_slots(gang)
        assert slots["Affiliation"].chosen == "Mutant"
        assert not slots["Favoured set"].is_resolved

    def test_what_the_gang_carries_though_a_fighter_was_asked(
        self, client, owner, gang, crew, archetypes
    ):
        """The offer says the gang holds what is chosen, so it does — and
        the Leader's slot still reads as the one that was settled."""
        client.force_login(owner)
        self.post(
            client, sheet_slots(gang)["Sorrow: Archetype"].href, archetypes["Brawler"]
        )

        chosen = Assignment.objects.get(affiliation=archetypes["Brawler"])
        assert chosen.gang == gang and chosen.miniature is None
        assert sheet_slots(gang)["Sorrow: Archetype"].chosen == "Brawler"
        assert_reconciled(gang)

    def test_a_gang_carried_question_is_chosen_for_per_fighter(
        self, client, owner, gang, crew, profiles, archetypes, skills
    ):
        """The skill offer rides the gang type and reaches every Leader.
        The chosen row names the Leader whose slot was clicked, and nobody
        else's slot moves."""
        choose(gang_anchor(gang, "Outcast Leader", crew), archetypes["Brawler"])
        second = hire_with_option(gang, profiles["leader"], "Ash")

        client.force_login(owner)
        self.post(
            client,
            sheet_slots(gang)["Sorrow: Primary skill"].href,
            skills["Berserker"],
        )

        chosen = Assignment.objects.get(skill=skills["Berserker"])
        assert chosen.miniature == crew["leader"]
        # Once chosen for, a skill question stops being asked and the skill
        # named joins that fighter's Skills row. The other Leader is still
        # being asked, on a slot of her own.
        sorrow = next(c for c in render_gang(gang).models if c.name == "Sorrow")
        assert "Berserker" in [line.name for line in sorrow.skills]
        slots = sheet_slots(gang)
        assert "Sorrow: Primary skill" not in slots
        assert not slots["Ash: Primary skill"].is_resolved
        assert second.name == "Ash"
        assert_reconciled(gang)

    def test_answering_again_leaves_the_other_fighters_answer_alone(
        self, client, owner, gang, crew, profiles, archetypes, skills
    ):
        """One question broadcast onto two cards is two questions.

        The skill offer rides the gang type and reaches every Leader, so
        both Leaders' answers hang off the one line that asked and name
        the one offer. Only the fighter whose card was clicked tells them
        apart — so changing one Leader's mind leaves the other Leader's
        skill exactly where it is.
        """
        # The Primary tier is empty until an archetype opens a set into it.
        choose(gang_anchor(gang, "Outcast Leader", crew), archetypes["Brawler"])
        ash = hire_with_option(gang, profiles["leader"], "Ash")
        client.force_login(owner)
        self.post(
            client, sheet_slots(gang)["Sorrow: Primary skill"].href, skills["Berserker"]
        )
        self.post(
            client, sheet_slots(gang)["Ash: Primary skill"].href, skills["Berserker"]
        )
        assert _skills_of(gang, "Sorrow") == ["Berserker"]
        assert _skills_of(gang, "Ash") == ["Berserker"]

        self.post(
            client,
            _slot_href(gang, crew["leader"], "Primary skill"),
            skills["Parry"],
        )

        assert _skills_of(gang, "Sorrow") == ["Parry"]
        assert _skills_of(gang, "Ash") == ["Berserker"]
        assert ash.name == "Ash"
        assert_reconciled(gang)

    def test_what_was_chosen_dies_with_its_carrier(
        self, client, owner, gang, crew, archetypes
    ):
        """What was chosen is caused by the row that asked, so retiring
        the Leader retires the gang's archetype with them."""
        client.force_login(owner)
        self.post(
            client, sheet_slots(gang)["Sorrow: Archetype"].href, archetypes["Brawler"]
        )
        assert gang_computed(gang).choices  # the gang carries the pick

        remove(crew["leader"].assignments.get(profile__isnull=False))
        assert not Assignment.objects.filter(
            affiliation=archetypes["Brawler"], archived=False
        ).exists()
        assert_reconciled(gang)

    def test_changing_your_mind_replaces_what_was_chosen(
        self, client, owner, gang, crew, affiliations
    ):
        """One question, one chosen thing: the old row is retired in the same
        click, so the slot never reads two things at once."""
        client.force_login(owner)
        href = sheet_slots(gang)["Affiliation"].href
        self.post(client, href, affiliations["Mutant"])
        self.post(
            client, sheet_slots(gang)["Affiliation"].href, affiliations["Clanless"]
        )

        assert sheet_slots(gang)["Affiliation"].chosen == "Clanless"
        assert not Assignment.objects.filter(
            affiliation=affiliations["Mutant"], archived=False
        ).exists()
        assert_reconciled(gang)

    def test_a_settled_slot_still_leads_somewhere(
        self, client, owner, gang, crew, affiliations
    ):
        client.force_login(owner)
        self.post(client, sheet_slots(gang)["Affiliation"].href, affiliations["Mutant"])
        settled = sheet_slots(gang)["Affiliation"]
        assert settled.is_resolved and settled.href

    def test_a_thing_that_is_not_on_offer_writes_nothing(
        self, client, owner, gang, crew, subtypes
    ):
        """A stale page or a tampered form. The list comes back; nothing
        is written and nothing is explained at length."""
        client.force_login(owner)
        before = Assignment.objects.count()
        response = self.post(
            client, sheet_slots(gang)["Affiliation"].href, subtypes["ganger"]
        )
        assert response.status_code == 302
        assert Assignment.objects.count() == before
        assert not sheet_slots(gang)["Affiliation"].is_resolved


class TestAClickTheDomainWillNotTake:
    """A click is met with words, whatever it names. Nothing a reader
    can send to one of these addresses is worth an error page: the whole
    of the flow is one list and one button, so the list is the reply."""

    def post(self, client, href, thing):
        return client.post(href, {"thing": f"{thing._meta.label_lower}:{thing.pk}"})

    def test_a_power_cannot_be_chosen_for_a_question_about_skills(
        self, client, owner, gang, crew, archetypes, whispers
    ):
        """A power filed in the fighter's Primary tier, clicked at the
        skill question. It is not on the list, so the click writes
        nothing, says why, and comes back to the list."""
        choose(gang_anchor(gang, "Outcast Leader", crew), archetypes["Brawler"])
        client.force_login(owner)
        href = sheet_slots(gang)["Sorrow: Primary skill"].href
        before = Assignment.objects.count()

        response = self.post(client, href, whispers["Mind Lock"])

        assert response.status_code == 302
        assert Assignment.objects.count() == before
        assert sheet_slots(gang)["Sorrow: Primary skill"].is_resolved is False
        assert (
            "not one of the things available to pick"
            in client.get(href).content.decode()
        )

    def test_a_pick_of_the_wrong_kind_is_refused_in_words(self, gang, crew, whispers):
        """The operation's own guard, under whatever asks it. A pick that
        cannot resolve the slot is declined with a sentence a player could
        read, and the transaction unwinds — so no surface can leave a row
        that settles nothing."""
        from n26.core.operations import Refusal, operation

        before = Assignment.objects.count()
        with pytest.raises(Refusal) as refused:
            with operation(gang, actor=gang.owner) as op:
                op.choose(
                    gang.founding, whispers["Mind Lock"], miniature=crew["leader"]
                )

        assert str(refused.value) == "Outcasts does not offer a choice of power."
        assert Assignment.objects.count() == before


class TestAddressesThatShouldNotResolve:
    def test_a_slot_that_no_longer_exists(self, client, owner, gang, crew, archetypes):
        """A carrier that has gone takes its question with it, and the
        address stops resolving."""
        client.force_login(owner)
        href = sheet_slots(gang)["Sorrow: Archetype"].href
        remove(crew["leader"].assignments.get(profile__isnull=False))
        assert client.get(href).status_code == 404

    def test_a_malformed_address(self, client, owner, gang, crew):
        client.force_login(owner)
        assert (
            client.get(reverse("n26-choose", args=[gang.pk, "rubbish"])).status_code
            == 404
        )

    def test_a_fighter_from_another_roster(self, client, owner, gang, crew, profiles):
        """The card in the address must be on the gang in the address —
        both the reader's here, so this is the roster check and not the
        ownership one."""
        other = found_gang("The Others", gang.gang_type, owner=owner)
        client.force_login(owner)
        href = sheet_slots(gang)["Sorrow: Archetype"].href
        stolen = href.replace(str(gang.pk), str(other.pk), 1)
        assert client.get(stolen).status_code == 404


class TestTheStripCostsNothing:
    def test_pointing_the_slots_at_their_pickers_adds_no_queries(
        self, django_assert_num_queries, gang, crew, profiles
    ):
        """The address is already on the line; turning it into a URL is
        arithmetic. A roster that grows must not grow the sheet's query
        count, slots or no slots."""
        from n26.core.views.choose import link_slots

        def budget():
            sheet = render_gang(gang)
            with django_assert_num_queries(0):
                link_slots(gang, sheet, *sheet.models)
            return sheet

        assert len(budget().models) == 2
        for name in ("Ash", "Kite", "Vex"):
            hire_with_option(gang, profiles["leader"], name)
        assert len(budget().models) == 5


class TestOneLineAskingTwice:
    """A line may ask two questions of one kind — a primary role and a
    secondary one — and the answers stay apart.

    Nothing about a pick itself says which question it settles: both take
    the same sort of thing, and the offers match on kind alone. So the
    pick names the question, exactly as a slot's pick names its slot, and
    an answer settles one question and no more.
    """

    @pytest.fixture
    def twice_asked(self, person_type, gang_list, skills_collection):
        """One subtype, two questions over one kind: a skill from the
        wide tier, and one from the narrow tier beside it."""
        _, tiers = skills_collection
        carrier = create_subtype("Twice Asked")
        for label, section in [
            ("Primary role", tiers["other"]),
            ("Secondary role", tiers["primary"]),
        ]:
            modifier(
                f"Twice Asked: {label}",
                targets_model(),
                offers_choice(Skill, from_section=section, label=label),
                carried_by=carrier,
            )
        profile = create_profile("Twice Asked", person_type, gang_list, price=0)
        profile.built_ins = create_default_set("Twice Asked kit", members=[carrier])
        profile.save()
        return profile

    def rows(self, fighter):
        return {row.kind_label: row for row in fighter_computed(fighter).choices}

    def test_answering_one_leaves_the_other_open(self, gang, twice_asked, skills):
        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)

        choose(
            rows["Primary role"].anchor.assignment,
            skills["Berserker"],
            offer=rows["Primary role"].offer,
        )

        settled = self.rows(vex)
        assert settled["Primary role"].chosen_name == "Berserker"
        assert settled["Secondary role"].chosen_name is None
        assert_reconciled(gang)

    def test_each_question_holds_its_own_answer(self, gang, twice_asked, skills):
        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)
        for label, skill in [
            ("Primary role", "Berserker"),
            ("Secondary role", "Marksman"),
        ]:
            choose(
                rows[label].anchor.assignment, skills[skill], offer=rows[label].offer
            )

        settled = self.rows(vex)
        assert settled["Primary role"].chosen_name == "Berserker"
        assert settled["Secondary role"].chosen_name == "Marksman"
        assert_reconciled(gang)

    def test_a_pick_naming_no_question_settles_one_and_only_one(
        self, gang, twice_asked, skills
    ):
        """A pick written before questions could be named: the offers'
        own selectors are all there is to go on, so it settles the first
        that matches rather than nothing at all — and only that one, so
        the other question is still there to be answered."""
        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)

        # Nobody said which question, and the line asks two that would
        # both take it, so the answer names neither — the shape of every
        # answer given before a question could be named.
        pick = choose(rows["Primary role"].anchor.assignment, skills["Marksman"])
        assert pick.chosen_for_offer is None

        settled = self.rows(vex)
        # Either question would take it: both offers match on kind alone.
        assert settled["Primary role"].chosen_name == "Marksman"
        assert settled["Secondary role"].chosen_name is None

    def test_an_unnamed_pick_leaves_the_other_question_answerable(
        self, gang, twice_asked, skills
    ):
        """And the question it left open still answers for itself."""
        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)
        choose(rows["Primary role"].anchor.assignment, skills["Marksman"])

        open_row = self.rows(vex)["Secondary role"]
        choose(open_row.anchor.assignment, skills["Parry"], offer=open_row.offer)

        settled = self.rows(vex)
        assert settled["Primary role"].chosen_name == "Marksman"
        assert settled["Secondary role"].chosen_name == "Parry"
        assert_reconciled(gang)

    def test_an_answer_given_is_never_taken_by_the_other_question(
        self, gang, twice_asked, skills
    ):
        """An unnamed answer settles whichever question is free, so it must
        not be the one whose own answer is sitting right there. Answering
        the second question first is the order that catches it."""
        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)
        choose(rows["Secondary role"].anchor.assignment, skills["Marksman"])

        open_row = self.rows(vex)["Primary role"]
        choose(open_row.anchor.assignment, skills["Parry"], offer=open_row.offer)

        settled = self.rows(vex)
        assert settled["Primary role"].chosen_name == "Parry"
        assert settled["Secondary role"].chosen_name == "Marksman"

    def test_rewording_a_question_does_not_empty_the_cards_that_answered_it(
        self, gang, twice_asked, skills
    ):
        """Composing a modifier writes its question afresh, so an answer
        can end up naming a question the card no longer asks. It is read
        like an unnamed one rather than lost."""
        from n26.library.models import OffersChoice

        vex = hire(gang, twice_asked, "Vex")
        rows = self.rows(vex)
        row = rows["Primary role"]
        choose(row.anchor.assignment, skills["Berserker"], offer=row.offer)

        # The question it named is gone; the answer stays where it is.
        gone = OffersChoice.objects.create(
            of_kind=row.offer.of_kind, label="Reworded", from_section=None
        )
        Assignment.objects.filter(skill=skills["Berserker"]).update(
            chosen_for_offer=gone
        )

        assert self.rows(vex)["Primary role"].chosen_name == "Berserker"

    def test_deleting_the_question_leaves_the_answer_standing(
        self, gang, twice_asked, skills
    ):
        """An author may delete or recompose a question at any time, and
        composing writes a new row either way. Whoever answered it keeps
        their answer, and the page they answered from still works."""
        from n26.library.authoring import delete_modifier
        from n26.library.models import Modifier

        vex = hire(gang, twice_asked, "Vex")
        row = self.rows(vex)["Primary role"]
        choose(row.anchor.assignment, skills["Berserker"], offer=row.offer)

        delete_modifier(Modifier.objects.get(name="Twice Asked: Primary role"))

        held = Assignment.objects.get(skill=skills["Berserker"])
        assert held.chosen_for_offer is None
        # The question is gone, so only the other one is asked — and the
        # answer is still the gang's, on the ledger where it always was.
        assert list(self.rows(vex)) == ["Secondary role"]
        assert_reconciled(gang)


# --- Putting an offer out of sight ---------------------------------------
#
# A gang list offers picks the player knows they will never take — a
# Choose they scroll past on every visit. There is nothing to delete: the
# offer is computed from its carrier, and only what is chosen is ever
# stored. So the owner dismisses it instead, and the sheet, the model's
# own page and the printed roster all stop drawing it. It is a guide, not
# a rule, and a dismissal is a row the owner can take back.


def dismiss_url(gang, line):
    return reverse("n26-dismiss-offer", args=[gang.pk, line.key])


def restore_url(gang, line):
    return reverse("n26-restore-offer", args=[gang.pk, line.key])


def sheet_body(client, gang, **query):
    url = reverse("n26-gang", args=[gang.pk])
    return client.get(url, query).content.decode()


def edit_body(client, miniature, **query):
    url = reverse("n26-edit-fighter", args=[miniature.pk])
    return client.get(url, query).content.decode()


def dismissed_tab(gang):
    return reverse("n26-edit-gang", args=[gang.pk]) + "?tab=dismissed"


def dismissed_keys(gang):
    return set(gang.dismissed_offers.values_list("slot_key", flat=True))


@pytest.fixture
def model_choices(gang, crew, profiles):
    from n26.core.operations import operation
    from n26.library.authoring import (
        add_built_in,
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
        create_wargear,
        create_weapon,
    )
    from n26.library.models import Power, Rule

    create_power("Test power", "Double")
    modifier(
        "Leader chooses a power",
        targets_model(),
        offers_choice(Power),
        carried_by=profiles["leader"],
    )
    kind = create_slot_type("Augmentation")
    pick = create_pickable("Tier 1", kind)
    table = create_picklist("Weapon tiers", kind, members=[pick])
    slot = create_slot("Weapon augmentation", kind, table, label="Augmentation")
    weapon = create_weapon("Augmentable gun", profiles=[("", 0)])
    add_built_in(weapon, slot)
    gear_pick = create_pickable("Gear tier 1", kind, rating_contribution=15)
    tier_rule = Rule.objects.create(name="Reinforced plating")
    modifier("Gear tier effect", targets_model(), adds(tier_rule), carried_by=gear_pick)
    gear_table = create_picklist("Gear tiers", kind, members=[gear_pick])
    gear_slot = create_slot("Wargear augmentation", kind, gear_table, label="Gear tier")
    wargear = create_wargear("Augmentable rig")
    add_built_in(wargear, gear_slot)
    with operation(gang, actor=gang.owner) as op:
        op.buy(crew["leader"], thing=weapon, paid=0)
        op.buy(crew["leader"], thing=wargear, paid=0)
    assert_reconciled(gang)
    return {
        label: sheet_slots(gang)[f"Sorrow: {label}"]
        for label in (
            "Archetype",
            "Primary skill",
            "Power",
            "Augmentation",
            "Gear tier",
        )
    }


def test_wargear_tier_stays_beneath_its_exact_carried_item(gang, crew, model_choices):
    card = next(card for card in render_gang(gang).models if card.name == "Sorrow")
    rig = next(line for line in card.equipment if line.name == "Augmentable rig")
    assert [choice.kind_label for choice in rig.choices] == ["Gear tier"]
    assert "Gear tier" not in [choice.kind_label for choice in card.row_questions]


def test_identical_wargear_copies_keep_their_own_tiers(gang, crew, model_choices):
    from n26.core.operations import operation
    from n26.library.models import Wargear

    with operation(gang, actor=gang.owner) as op:
        op.buy(
            crew["leader"],
            thing=Wargear.objects.get(name="Augmentable rig"),
            paid=0,
        )
    card = next(card for card in render_gang(gang).models if card.name == "Sorrow")
    rigs = [line for line in card.equipment if line.name == "Augmentable rig"]
    assert len(rigs) == 2
    assert all(
        [choice.kind_label for choice in rig.choices] == ["Gear tier"] for rig in rigs
    )


def test_gang_sheet_choice_links_return_to_the_exact_sheet(
    client, owner, gang, model_choices
):
    from urllib.parse import parse_qs, urlsplit

    from bs4 import BeautifulSoup

    client.force_login(owner)
    here = reverse("n26-gang", args=[gang.pk])
    page = BeautifulSoup(client.get(here).content, "html.parser")
    assert "Gear tier: —" in page.get_text(" ", strip=True)
    prefix = reverse("n26-choose", args=[gang.pk, model_choices["Archetype"].key])
    link = page.find("a", href=lambda value: value and value.startswith(prefix))
    assert parse_qs(urlsplit(link["href"]).query)["return"] == [here]


def test_picker_explains_an_options_effect_and_rating(gang, model_choices):
    option = next(
        option
        for group in offer_for(model_choices["Gear tier"]).groups
        for option in group.options
    )
    assert option.rating == 15
    assert "Reinforced plating" in option.effect_summary


def test_picker_effect_help_has_fixed_query_growth(gang, model_choices):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.core.views.choose import find_slot
    from n26.library.models import Pickable, PicklistMember

    line = model_choices["Gear tier"]
    found = find_slot(gang, line.key)
    with CaptureQueriesContext(connection) as one:
        build_choice_offer(found.slot, found.computed)
    picklist = found.slot.slot.picklist
    for position in range(2, 11):
        pick = Pickable.objects.create(
            name=f"Gear tier {position}",
            slot_type=picklist.slot_type,
            rating_contribution=position,
        )
        PicklistMember.objects.create(
            picklist=picklist, pickable=pick, position=position
        )
    found = find_slot(gang, line.key)
    with CaptureQueriesContext(connection) as ten:
        build_choice_offer(found.slot, found.computed)
    assert len(ten) == len(one)


class TestTheXBesideAnOpenOffer:
    """An open offer the owner may dismiss ends in an X. Nobody else is
    offered one, and an offer holding a pick is not either."""

    def test_each_choice_and_dismiss_button_share_a_gapless_aligned_group(
        self, client, owner, gang, crew, model_choices
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        page = BeautifulSoup(edit_body(client, crew["leader"]), "html.parser")
        for line in model_choices.values():
            form = page.find("form", action=dismiss_url(gang, line))
            group = form.parent
            assert {"items-center", "gap-0"} <= set(group["class"])
            assert group.find(
                "a",
                href=lambda href, prefix=line.href: href and href.startswith(prefix),
            )
            assert "py-0!" not in form.find("button")["class"]
        page = BeautifulSoup(sheet_body(client, gang), "html.parser")
        form = page.find(
            "form", action=dismiss_url(gang, sheet_slots(gang)["Affiliation"])
        )
        group = form.find_parent("dd")
        assert {"items-center", "gap-0"} <= set(group["class"])
        assert "ms-1" not in form.parent["class"]

    def test_the_owner_sees_the_x_on_the_sheet_and_the_models_page(
        self, client, owner, gang, crew
    ):
        client.force_login(owner)
        slots = sheet_slots(gang)
        body = sheet_body(client, gang)
        assert dismiss_url(gang, slots["Affiliation"]) in body
        assert dismiss_url(gang, slots["Sorrow: Archetype"]) in body
        assert dismiss_url(gang, slots["Sorrow: Primary skill"]) in body
        page = edit_body(client, crew["leader"])
        assert dismiss_url(gang, slots["Sorrow: Archetype"]) in page
        assert dismiss_url(gang, slots["Sorrow: Primary skill"]) in page

    def test_a_reader_who_does_not_own_the_gang_gets_no_x(
        self, client, gang, crew, django_user_model
    ):
        client.force_login(django_user_model.objects.create_user("reader"))
        body = sheet_body(client, gang)
        assert "Affiliation" in body
        assert "/offers/" not in body

    def test_an_offer_holding_a_pick_has_no_x(
        self, client, owner, gang, crew, affiliations
    ):
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(
            line.href, {"thing": f"library.affiliation:{affiliations['Mutant'].pk}"}
        )
        body = sheet_body(client, gang)
        assert "Mutant" in body
        assert dismiss_url(gang, line) not in body


class TestDismissingAnOffer:
    """One click, one row, and the offer is gone from every reading of
    the gang — the owner's sheet, a stranger's, the model's page and the
    printed roster."""

    def test_the_offer_leaves_every_screen(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Primary skill"]
        response = client.post(dismiss_url(gang, line))
        assert response.status_code == 302
        assert response["Location"] == reverse("n26-gang", args=[gang.pk])
        assert dismissed_keys(gang) == {line.key}

        assert line.href not in sheet_body(client, gang)
        assert line.href not in edit_body(client, crew["leader"])
        for route in ("n26-equip", "n26-fighter-options"):
            page = client.get(reverse(route, args=[crew["leader"].pk]))
            assert page.status_code == 200
            assert dismiss_url(gang, line) not in page.content.decode()
            assert restore_url(gang, line) not in page.content.decode()
        printed = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        assert "Primary skill" not in printed
        assert "Archetype" in printed, "the offer beside it still prints"

    def test_a_stranger_stops_seeing_it_too(
        self, client, owner, gang, crew, django_user_model
    ):
        line = sheet_slots(gang)["Affiliation"]
        DismissedOffer.objects.create(gang=gang, slot_key=line.key)
        client.force_login(django_user_model.objects.create_user("reader"))
        body = sheet_body(client, gang)
        assert "Favoured set" in body
        assert "Affiliation" not in body

    def test_the_gangs_own_offer_goes_from_the_strip(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(dismiss_url(gang, line))
        body = sheet_body(client, gang)
        assert line.href not in body
        assert sheet_slots(gang)["Favoured set"].href in body

    def test_it_lands_back_where_it_was_clicked(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        back = reverse("n26-edit-fighter", args=[crew["leader"].pk])
        response = client.post(dismiss_url(gang, line), {"back": back})
        assert response["Location"] == back

    def test_an_address_off_this_site_is_not_followed(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        response = client.post(
            dismiss_url(gang, line), {"back": "https://elsewhere.example/"}
        )
        assert response["Location"] == reverse("n26-gang", args=[gang.pk])

    def test_a_second_click_writes_no_second_row(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        client.post(dismiss_url(gang, line))
        assert gang.dismissed_offers.count() == 1

    def test_an_offer_holding_a_pick_is_refused(
        self, client, owner, gang, crew, affiliations
    ):
        """The control was drawn before the pick landed: what was chosen
        is drawn, and nothing is written."""
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(
            line.href, {"thing": f"library.affiliation:{affiliations['Mutant'].pk}"}
        )
        response = client.post(dismiss_url(gang, line), follow=True)
        assert (
            "You cannot dismiss Affiliation. It has a pick. Take the pick back first."
            in response.content.decode()
        )
        assert dismissed_keys(gang) == set()

    def test_the_x_is_a_post(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        assert client.get(dismiss_url(gang, line)).status_code == 405
        assert dismissed_keys(gang) == set()


class TestDismissalAddressesThatShouldNotResolve:
    def test_an_offer_that_no_longer_exists(self, client, owner, gang, crew):
        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        url = dismiss_url(gang, line).replace(line.key, "nobody:nothing:none")
        assert client.post(url).status_code == 404

    def test_somebody_elses_gang(self, client, gang, crew, django_user_model):
        client.force_login(django_user_model.objects.create_user("reader"))
        line = sheet_slots(gang)["Sorrow: Archetype"]
        assert client.post(dismiss_url(gang, line)).status_code == 404
        assert client.post(restore_url(gang, line)).status_code == 404


class TestShowingDismissedOffers:
    """Restore choices from the model's or gang's Edit page."""

    def test_the_empty_tab_is_linked_from_every_gang_edit_screen(
        self, client, owner, gang
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        at = reverse("n26-edit-gang", args=[gang.pk])
        for url in (
            at,
            f"{at}?tab=notes",
            reverse("n26-gang-trade-points", args=[gang.pk]),
        ):
            response = client.get(url)
            assert response.status_code == 200
            assert dismissed_tab(gang) in response.content.decode()
        response = client.get(dismissed_tab(gang))
        page = BeautifulSoup(response.content, "html.parser")
        assert page.find("a", href=dismissed_tab(gang))["aria-current"] == "page"
        assert "No dismissed gang choices." in page.get_text()
        assert page.find("input", attrs={"name": "name"}) is None
        assert page.find("textarea") is None
        assert "Save changes" not in page.get_text()

    def test_restoring_the_last_gang_choice_returns_to_the_empty_tab(
        self, client, owner, gang, crew
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(dismiss_url(gang, line))
        page = BeautifulSoup(client.get(dismissed_tab(gang)).content, "html.parser")
        form = page.find("form", action=restore_url(gang, line))
        assert form["method"] == "post"
        assert form.find_parent("form") is None
        assert form.find("button")["aria-label"] == "Restore Affiliation"
        assert "bg-transparent" in form.find("button")["class"]
        data = {
            field["name"]: field.get("value", "") for field in form.find_all("input")
        }
        assert data["csrfmiddlewaretoken"]
        assert data["back"] == dismissed_tab(gang)
        assert client.get(form["action"]).status_code == 405
        response = client.post(form["action"], data, follow=True)
        assert response.redirect_chain == [(dismissed_tab(gang), 302)]
        assert "No dismissed gang choices." in response.content.decode()
        assert not dismissed_keys(gang)
        assert line.href in sheet_body(client, gang)

    def test_the_dismissed_tab_is_owner_only(self, client, gang, django_user_model):
        assert client.get(dismissed_tab(gang)).status_code == 302
        client.force_login(django_user_model.objects.create_user("reader"))
        assert client.get(dismissed_tab(gang)).status_code == 404

    def test_resolved_and_missing_choices_are_not_listed(
        self, client, owner, gang, crew, affiliations
    ):
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(
            line.href, {"thing": f"library.affiliation:{affiliations['Mutant'].pk}"}
        )
        for key in (line.key, "nobody:nothing:none"):
            DismissedOffer.objects.create(gang=gang, slot_key=key)
        response = client.get(dismissed_tab(gang))
        assert "No dismissed gang choices." in response.content.decode()
        assert restore_url(gang, line) not in response.content.decode()

    def test_an_external_restore_return_address_falls_back_to_the_tab(
        self, client, owner, gang, crew
    ):
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(dismiss_url(gang, line))
        response = client.post(
            restore_url(gang, line), {"back": "https://elsewhere.example/"}
        )
        assert response["Location"] == dismissed_tab(gang)

    def test_an_empty_picklist_can_be_dismissed_and_restored(
        self, client, owner, gang, crew
    ):
        """Dismissal hides an unwanted prompt even when it offers no picks."""
        from n26.core.operations import operation
        from n26.library.authoring import create_picklist, create_slot, create_slot_type

        kind = create_slot_type("Empty choice")
        table = create_picklist("Empty list", kind)
        slot = create_slot("Empty choice", kind, table)
        with operation(gang, actor=owner) as op:
            op.assign(slot, miniature=crew["leader"])
        line = sheet_slots(gang)["Sorrow: Empty choice"]
        assert offer_for(line).is_empty
        client.force_login(owner)
        assert dismiss_url(gang, line) in edit_body(client, crew["leader"])
        assert client.post(dismiss_url(gang, line)).status_code == 302
        assert line.key in dismissed_keys(gang)
        assert restore_url(gang, line) in edit_body(client, crew["leader"])
        client.post(restore_url(gang, line))
        assert line.key not in dismissed_keys(gang)
        assert dismiss_url(gang, line) in edit_body(client, crew["leader"])

    def test_options_saves_and_dialogs_keep_restore_available_on_edit(
        self, client, owner, gang, crew
    ):
        from bs4 import BeautifulSoup

        from n26.core.operations import operation
        from n26.library.authoring import create_wargear

        client.force_login(owner)
        miniature = crew["leader"]
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        with operation(gang, actor=owner) as op:
            item = op.buy(miniature, thing=create_wargear("Knife"), paid=0)
        here = reverse("n26-fighter-options", args=[miniature.pk])
        page = BeautifulSoup(
            client.get(f"{here}?dismissed=show").content, "html.parser"
        )
        sell = next(
            link["href"]
            for link in page.find_all("a", href=True)
            if f"sell={item.pk}" in link["href"]
        )
        dialog = client.get(sell)
        assert dialog.status_code == 200
        assert restore_url(gang, line) in dialog.content.decode()
        response = client.post(here, follow=True)
        assert response.status_code == 200
        assert restore_url(gang, line) not in response.content.decode()
        assert restore_url(gang, line) in edit_body(client, miniature)
        assert line.key in dismissed_keys(gang)
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_every_kind_of_model_choice_is_restored_only_from_the_edit_grid(
        self, client, owner, gang, crew, model_choices
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        for line in model_choices.values():
            client.post(dismiss_url(gang, line))
        for query in ({}, {"dismissed": "show"}):
            page = BeautifulSoup(
                edit_body(client, crew["leader"], **query), "html.parser"
            )
            box = page.find(id="n26-dismissed-choices")
            card = page.find(id="n26-model-card-host")
            assert "contents" in box["class"]
            assert "grid" in box.parent["class"]
            assert "self-start" in box.find(recursive=False)["class"]
            assert "Lore" in box.find_previous_sibling().get_text()
            assert box.find_parent(attrs={"role": "menu"}) is None
            assert box.find_parent(id="n26-model-card-host") is None
            assert "Dismissed choices" in box.get_text()
            assert len(box.find_all("form")) == len(model_choices)
            for line in model_choices.values():
                assert box.find("form", action=restore_url(gang, line))
                assert line.kind_label not in card.get_text()
                assert restore_url(gang, line) not in sheet_body(client, gang, **query)
            for route in ("n26-equip", "n26-fighter-options"):
                body = client.get(
                    reverse(route, args=[crew["leader"].pk]), query
                ).content.decode()
                assert "n26-dismissed-choices" not in body
                assert all(
                    restore_url(gang, line) not in body
                    for line in model_choices.values()
                )
        other_model = edit_body(client, crew["ganger"])
        assert all(
            restore_url(gang, line) not in other_model
            for line in model_choices.values()
        )

    def test_choice_controls_are_ghost_buttons_including_chosen_values(
        self, client, owner, gang, crew, model_choices, affiliations
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        affiliation = sheet_slots(gang)["Affiliation"]
        client.post(
            affiliation.href,
            {"thing": f"library.affiliation:{affiliations['Mutant'].pk}"},
        )
        for body in (edit_body(client, crew["leader"]), sheet_body(client, gang)):
            controls = BeautifulSoup(body, "html.parser").select('a[href*="/choose/"]')
            assert controls
            for control in controls:
                assert "bg-transparent" in control["class"]
                assert "rounded-button" in control["class"]
                assert "hover:underline" not in control["class"]

    def test_a_redrawn_dismissed_card_appears_and_clears_its_last_choice(
        self, client, owner, gang, crew
    ):
        from bs4 import BeautifulSoup

        from n26.core.operations import operation
        from n26.library.authoring import create_counter

        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        with operation(gang, actor=owner) as op:
            counter = op.assign(create_counter("Tally"), miniature=crew["leader"])
        here = reverse("n26-edit-fighter", args=[crew["leader"].pk])
        for state in ("empty", "dismissed", "restored"):
            if state == "dismissed":
                client.post(dismiss_url(gang, line), {"back": here})
            elif state == "restored":
                client.post(restore_url(gang, line), {"back": here})
            response = client.post(
                reverse("n26-tally", args=[counter.pk]),
                {"change": "1", "back": here},
                headers={"HX-Request": "true"},
            )
            box = BeautifulSoup(response.content, "html.parser").find(
                id="n26-dismissed-choices"
            )
            assert box["hx-swap-oob"] == "outerHTML"
            assert "contents" in box["class"]
            assert bool(box.find("form")) == (state == "dismissed")
            assert bool(box.find(recursive=False)) == (state == "dismissed")
            full_page_box = BeautifulSoup(
                edit_body(client, crew["leader"]), "html.parser"
            ).find(id="n26-dismissed-choices")
            assert bool(full_page_box.find(recursive=False)) == (state == "dismissed")

    @pytest.mark.parametrize("query", ({}, {"dismissed": "show"}))
    def test_the_sheet_never_shows_dismissed_choices_or_restore_controls(
        self, client, owner, gang, crew, query
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        assert "Dismissed choices" not in sheet_body(client, gang)
        slots = sheet_slots(gang)
        for label in ("Affiliation", "Sorrow: Archetype"):
            client.post(dismiss_url(gang, slots[label]))
        body = sheet_body(client, gang, **query)
        page = BeautifulSoup(body, "html.parser")
        assert not any(
            "Dismissed choices" in term.get_text() for term in page.find_all("dt")
        )
        assert "?dismissed=show" not in body
        # Neither offer is drawn, and neither Restore is.
        assert restore_url(gang, slots["Affiliation"]) not in body
        assert slots["Affiliation"].href not in body

    def test_the_dismissed_tab_lists_only_gang_choices(self, client, owner, gang, crew):
        client.force_login(owner)
        slots = sheet_slots(gang)
        client.post(dismiss_url(gang, slots["Affiliation"]))
        client.post(dismiss_url(gang, slots["Sorrow: Archetype"]))
        body = client.get(dismissed_tab(gang)).content.decode()
        assert restore_url(gang, slots["Affiliation"]) in body
        assert restore_url(gang, slots["Sorrow: Archetype"]) not in body
        assert "Dismissed" in body
        # Shown is not restored: the Choose stays away.
        assert slots["Affiliation"].href not in body
        assert dismiss_url(gang, slots["Affiliation"]) not in body

    def test_the_models_own_page_shows_and_restores(self, client, owner, gang, crew):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        page = edit_body(client, crew["leader"])
        assert "Dismissed choices" in page
        assert line.href not in page
        box = BeautifulSoup(page, "html.parser").find(id="n26-dismissed-choices")
        form = box.find("form", action=restore_url(gang, line))
        assert form["method"] == "post"
        assert form.find("button").get_text(strip=True) == "Restore"
        assert form.find("button")["aria-label"] == "Restore Archetype"
        data = {
            field["name"]: field.get("value", "") for field in form.find_all("input")
        }
        back = reverse("n26-edit-fighter", args=[crew["leader"].pk])
        assert data["back"] == back
        response = client.post(form["action"], data)
        assert response["Location"] == back
        assert dismissed_keys(gang) == set()
        assert line.href in edit_body(client, crew["leader"])

    def test_restoring_without_a_return_address_keeps_the_tab_open(
        self, client, owner, gang, crew
    ):
        client.force_login(owner)
        slots = sheet_slots(gang)
        client.post(dismiss_url(gang, slots["Affiliation"]))
        client.post(dismiss_url(gang, slots["Favoured set"]))
        response = client.post(restore_url(gang, slots["Affiliation"]))
        assert response["Location"] == dismissed_tab(gang)
        body = client.get(response["Location"]).content.decode()
        assert slots["Affiliation"].href not in body
        assert slots["Affiliation"].href in sheet_body(client, gang)
        assert restore_url(gang, slots["Favoured set"]) in body

    def test_dismissing_from_a_legacy_show_url_returns_to_the_clean_sheet(
        self, client, owner, gang, crew
    ):
        from bs4 import BeautifulSoup

        client.force_login(owner)
        slots = sheet_slots(gang)
        client.post(dismiss_url(gang, slots["Affiliation"]))
        body = sheet_body(client, gang, dismissed="show")
        sheet = reverse("n26-gang", args=[gang.pk])
        form = BeautifulSoup(body, "html.parser").find(
            "form", action=dismiss_url(gang, slots["Favoured set"])
        )
        data = {
            field["name"]: field.get("value", "") for field in form.find_all("input")
        }
        assert data["back"] == sheet
        response = client.post(
            dismiss_url(gang, slots["Favoured set"]),
            data,
            follow=True,
        )
        assert response.redirect_chain == [(sheet, 302)]
        landed = response.content.decode()
        assert restore_url(gang, slots["Affiliation"]) not in landed
        assert restore_url(gang, slots["Favoured set"]) not in landed

    def test_a_pick_landing_on_a_dismissed_offer_takes_the_dismissal_off(
        self, client, owner, gang, crew, affiliations
    ):
        """The pick screen is still reachable — an old link, the browser's
        history — and choosing there is the owner changing their mind: the
        dismissal goes, so taking the pick back later leaves the offer
        open rather than hiding it again unasked."""
        client.force_login(owner)
        line = sheet_slots(gang)["Affiliation"]
        client.post(dismiss_url(gang, line))
        client.post(
            line.href, {"thing": f"library.affiliation:{affiliations['Mutant'].pk}"}
        )
        assert dismissed_keys(gang) == set()
        client.post(line.href, {"thing": NONE_KEY})
        assert line.href in sheet_body(client, gang)

    def test_a_skill_ticked_on_the_models_page_takes_the_dismissal_off(
        self, client, owner, gang, crew, skills, archetypes
    ):
        """The pick screen is not the only way to settle an offer: a tick
        in the skills box on the model's own page writes the same pick,
        where the skill is on the question's own list. Whichever way it
        lands, the dismissal goes with it."""
        from n26.core.views.skills import _key

        client.force_login(owner)
        slots = sheet_slots(gang)
        # Brawler opens Combat as Primary, which is what puts Berserker
        # on the Primary skill question's list rather than beside it.
        client.post(
            slots["Sorrow: Archetype"].href,
            {"thing": f"library.affiliation:{archetypes['Brawler'].pk}"},
        )
        line = slots["Sorrow: Primary skill"]
        client.post(dismiss_url(gang, line))
        assert dismissed_keys(gang) == {line.key}
        response = client.post(
            reverse("n26-edit-fighter", args=[crew["leader"].pk]),
            {"act": "skills", "skills": [_key(skills["Berserker"])]},
        )
        assert response.status_code == 302
        assert _skills_of(gang, "Sorrow") == ["Berserker"]
        # The tick settled the question rather than standing beside it.
        assert "Sorrow: Primary skill" not in sheet_slots(gang)
        assert dismissed_keys(gang) == set()

    def test_a_dead_models_own_page_only_hides_them(self, client, owner, gang, crew):
        """The model's page draws the same dead card the sheet does: the
        dismissed offers go, and neither a way to show them nor a
        Restore is drawn."""
        from n26.core.operations import operation
        from n26.core.status import Status

        client.force_login(owner)
        slots = sheet_slots(gang)
        line = slots["Sorrow: Archetype"]
        still_open = slots["Sorrow: Primary skill"]
        client.post(dismiss_url(gang, line))
        with operation(gang, actor=owner) as op:
            op.set_status(crew["leader"], Status.DEAD)
        edit_body(client, crew["leader"])
        for query in ({}, {"dismissed": "show"}):
            page = edit_body(client, crew["leader"], **query)
            assert line.href not in page
            assert restore_url(gang, line) not in page
            assert "Dismissed choices" not in page
            # Nor an X on the offer still open: a dead card cannot show
            # the way back from a dismissal, so it offers none.
            assert dismiss_url(gang, still_open) not in page

    def test_a_dead_models_dismissed_offers_only_go(self, client, owner, gang, crew):
        """A dead model's card has nothing to click, so its dismissed
        offers are neither shown nor offered back — the card draws no
        control for them, and asking to see them draws no Restore."""
        from n26.core.operations import operation
        from n26.core.status import Status

        client.force_login(owner)
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        with operation(gang, actor=owner) as op:
            op.set_status(crew["leader"], Status.DEAD)
        # The dismissal's own confirmation names the control; one plain
        # read takes it, so the next is the sheet alone.
        sheet_body(client, gang)
        body = sheet_body(client, gang, dismissed="show")
        assert "Sorrow" in body
        assert line.href not in body
        assert restore_url(gang, line) not in body
        assert "Dismissed choices" not in body

    def test_the_redrawn_card_builds_its_control_from_this_site_only(
        self, rf, owner, gang, crew
    ):
        """A redrawn box's Restore form returns to this model's Edit page."""
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore

        from n26.core.views.edit import render_card_update

        line = sheet_slots(gang)["Sorrow: Archetype"]
        DismissedOffer.objects.create(gang=gang, slot_key=line.key)
        request = rf.get(reverse("n26-edit-fighter", args=[crew["leader"].pk]))
        request.user = owner
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        body = render_card_update(
            request, crew["leader"], "https://elsewhere.example/?dismissed=show"
        ).content.decode()
        assert "elsewhere.example" not in body
        edit = reverse("n26-edit-fighter", args=[crew["leader"].pk])
        assert f'name="back" value="{edit}"' in body
        assert restore_url(gang, line) in body

    @pytest.mark.parametrize(
        "route", ("n26-edit-fighter", "n26-equip", "n26-fighter-options")
    )
    def test_a_tally_updates_only_the_edit_screens_dismissed_choices_card(
        self, client, owner, gang, crew, route
    ):
        from n26.core.operations import operation
        from n26.library.authoring import create_counter

        client.force_login(owner)
        miniature = crew["leader"]
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        with operation(gang, actor=owner) as op:
            counter = op.assign(create_counter("Review tally"), miniature=miniature)
        here = reverse(route, args=[miniature.pk])
        shown = f"{here}?dismissed=show"
        page = client.get(shown)
        assert page.status_code == 200
        assert (restore_url(gang, line) in page.content.decode()) == (
            route == "n26-edit-fighter"
        )

        response = client.post(
            reverse("n26-tally", args=[counter.pk]),
            {"change": "1", "back": shown},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert (restore_url(gang, line) in body) == (route == "n26-edit-fighter")
        assert ('id="n26-dismissed-choices"' in body) == (route == "n26-edit-fighter")
        assert f'name="back" value="{shown}"' in body
        assert dismissed_keys(gang) == {line.key}

    @pytest.mark.parametrize("htmx", (False, True))
    def test_buying_and_selling_keep_dismissed_model_choices_off_the_card(
        self, client, owner, gang, crew, htmx
    ):
        from urllib.parse import parse_qs, urlsplit

        from bs4 import BeautifulSoup

        from n26.core.operations import operation
        from n26.library.authoring import create_wargear, create_weapon

        client.force_login(owner)
        miniature = crew["leader"]
        line = sheet_slots(gang)["Sorrow: Archetype"]
        client.post(dismiss_url(gang, line))
        knife = create_wargear("Knife", price=10)
        collection = create_collection("Equipment", entries=[knife])
        weapon = create_weapon("Autogun", price=5, profiles=[("", 0)])
        with operation(gang, actor=owner) as op:
            op.assign(collection, gang=gang)
            gun = op.buy(miniature, thing=weapon, paid=5)
        here = reverse("n26-equip", args=[miniature.pk])
        shown = f"{here}?list={collection.pk}&dismissed=show"
        page = BeautifulSoup(client.get(shown).content, "html.parser")
        action = page.find("form", id="equip-catalogue")["action"]
        assert parse_qs(urlsplit(action).query)["dismissed"] == ["show"]

        headers = {"HX-Request": "true"} if htmx else {}
        response = client.post(
            action, {"thing": f"library.wargear:{knife.pk}"}, headers=headers
        )
        if not htmx:
            assert response.url == shown
            response = client.get(response.url)
        assert response.status_code == 200
        assert restore_url(gang, line) not in response.content.decode()

        bought = Assignment.objects.get(miniature=miniature, wargear=knife)
        page = BeautifulSoup(
            client.get(f"{shown}&sell={bought.pk}").content, "html.parser"
        )
        form = page.find("form", action=reverse("n26-sell", args=[bought.pk]))
        assert form is not None
        data = {
            field["name"]: field.get("value", "")
            for field in form.find_all("input", type="hidden")
        }
        assert data["dismissed"] == "show"
        response = client.post(form["action"], data, headers=headers)
        if not htmx:
            assert response.url == shown
            response = client.get(response.url)
        else:
            assert response["HX-Replace-Url"] == shown
        assert response.status_code == 200
        assert restore_url(gang, line) not in response.content.decode()
        page = BeautifulSoup(response.content, "html.parser")
        accessory_form = page.find(
            "form", action=reverse("n26-accessorise", args=[gun.pk])
        )
        assert (
            accessory_form.find("input", attrs={"name": "dismissed"})["value"] == "show"
        )
        assert dismissed_keys(gang) == {line.key}
        assert_reconciled(gang)

    @pytest.mark.parametrize("screen", ("edit", "gang"))
    @pytest.mark.parametrize("htmx", (False, True))
    def test_equipment_dialogs_keep_dismissed_choices_on_their_edit_pages(
        self, client, owner, gang, crew, screen, htmx
    ):
        from urllib.parse import parse_qs, urlsplit

        from bs4 import BeautifulSoup

        from n26.core.operations import operation
        from n26.library.authoring import create_wargear

        client.force_login(owner)
        miniature = crew["leader"]
        line = sheet_slots(gang)[
            "Sorrow: Archetype" if screen == "edit" else "Affiliation"
        ]
        client.post(dismiss_url(gang, line))
        knife = create_wargear("Knife", price=10)
        with operation(gang, actor=owner) as op:
            bought = op.buy(
                miniature if screen == "edit" else gang.stash, thing=knife, paid=10
            )
        here = (
            reverse("n26-edit-fighter", args=[miniature.pk])
            if screen == "edit"
            else reverse("n26-gang", args=[gang.pk])
        )
        shown = f"{here}?dismissed=show" if screen == "edit" else here
        page = BeautifulSoup(client.get(shown).content, "html.parser")
        sell = next(
            link["href"]
            for link in page.find_all("a", href=True)
            if parse_qs(urlsplit(link["href"]).query).get("sell") == [str(bought.pk)]
        )
        assert parse_qs(urlsplit(sell).query).get("dismissed", []) == (
            ["show"] if screen == "edit" else []
        )

        headers = {"HX-Request": "true"} if htmx else {}
        response = client.get(sell, headers=headers)
        assert response.status_code == 200
        if not htmx:
            assert (restore_url(gang, line) in response.content.decode()) == (
                screen == "edit"
            )
        page = BeautifulSoup(response.content, "html.parser")
        form = page.find("form", action=reverse("n26-sell", args=[bought.pk]))
        assert form is not None
        data = {
            field["name"]: field.get("value", "")
            for field in form.find_all("input", type="hidden")
        }
        assert data.get("dismissed", "") == ("show" if screen == "edit" else "")
        assert not form.has_attr("hx-post")
        response = client.post(form["action"], data)
        assert response.status_code == 302
        assert response.url == shown
        assert (
            restore_url(gang, line) in client.get(response.url).content.decode()
        ) == (screen == "edit")
        if screen == "gang":
            assert (
                restore_url(gang, line)
                in client.get(dismissed_tab(gang)).content.decode()
            )
        assert dismissed_keys(gang) == {line.key}
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_row_left_behind_by_a_sold_carrier_can_still_be_taken_off(
        self, client, owner, gang, crew
    ):
        client.force_login(owner)
        DismissedOffer.objects.create(gang=gang, slot_key="nobody:nothing:none")
        response = client.post(
            reverse("n26-restore-offer", args=[gang.pk, "nobody:nothing:none"])
        )
        assert response.status_code == 302
        assert dismissed_keys(gang) == set()

    def test_a_stranger_is_not_shown_them_however_they_ask(
        self, client, gang, crew, django_user_model
    ):
        line = sheet_slots(gang)["Affiliation"]
        DismissedOffer.objects.create(gang=gang, slot_key=line.key)
        client.force_login(django_user_model.objects.create_user("reader"))
        body = sheet_body(client, gang, dismissed="show")
        assert "Affiliation" not in body
        assert "Dismissed choices" not in body


class TestWhatItCosts:
    def test_the_dismissed_tab_does_not_load_fighters_or_grow_with_the_roster(
        self, client, owner, gang, crew, profiles
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(owner)

        def queries():
            with CaptureQueriesContext(connection) as captured:
                response = client.get(dismissed_tab(gang))
            assert response.status_code == 200
            return [query["sql"] for query in captured]

        queries()
        before = queries()
        for name in ("Ash", "Kite"):
            hire_with_option(gang, profiles["leader"], name)
        for label, line in sheet_slots(gang).items():
            if label in {"Affiliation", "Favoured set", "Ash: Archetype"}:
                DismissedOffer.objects.create(gang=gang, slot_key=line.key)
        after = queries()
        assert len(after) == len(before)
        assert not any('FROM "n26_miniature"' in sql for sql in after)

    def test_the_sheet_pays_one_query_however_many_are_dismissed(
        self, client, owner, gang, crew, profiles, django_assert_num_queries
    ):
        """One read of what the gang has dismissed serves the whole sheet:
        a roster that grows, and a list of dismissals that grows with
        it, must not grow the count."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        client.force_login(owner)
        url = reverse("n26-gang", args=[gang.pk])

        def queries():
            with CaptureQueriesContext(connection) as captured:
                client.get(url)
            return len(captured)

        # The first request pays for the session and the caches it warms;
        # the comparison is between two requests after that.
        queries()
        before = queries()
        for name in ("Ash", "Kite"):
            hire_with_option(gang, profiles["leader"], name)
        slots = sheet_slots(gang)
        for label in ("Affiliation", "Ash: Archetype", "Kite: Primary skill"):
            DismissedOffer.objects.create(gang=gang, slot_key=slots[label].key)
        assert queries() == before

    def test_the_filter_itself_costs_nothing(
        self, gang, crew, django_assert_num_queries
    ):
        from n26.core.render import hide_dismissed

        sheet = render_gang(gang)
        keys = {line.key for card in sheet.models for line in card.questions}
        with django_assert_num_queries(0):
            hidden = sum(
                hide_dismissed(keys, holder) for holder in (sheet, *sheet.models)
            )
        assert hidden == 2
        assert all(not card.questions for card in sheet.models)
