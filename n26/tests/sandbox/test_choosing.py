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
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_choice_offer, render_gang
from n26.library.models import Affiliation, Skill
from n26.tests.sandbox.actions import (
    add_entry,
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
    from n26.core.views.choose import _find_slot

    gang = Assignment.objects.get(pk=slot_line.key.split(":")[1]).gang_root
    found = _find_slot(gang, slot_line.key)
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
