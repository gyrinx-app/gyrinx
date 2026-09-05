import pytest

from n26.core.card import build_card, build_modifier_index
from n26.core.cloning import clone_event_details
from n26.core.effects import compute
from n26.core.history import build, campaign_history, campaign_history_size
from n26.core.models import (
    Action,
    Assignment,
    AssignmentSet,
    Campaign,
    CampaignMembership,
    CounterValue,
    Gang,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    PrintConfig,
    StatOverride,
)
from n26.core.operations import NotEnoughCredits, Refusal, clone_gang, operation
from n26.core.reconcile import (
    assert_reconciled,
    trade_points_spent_by,
    trade_points_spent_for,
)
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    buy,
    create_affiliation,
    create_assignment_set,
    create_counter,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    create_subtype,
    create_wargear,
    create_weapon,
    ef_adds,
    found_gang,
    give_weapon,
    hire_with_option,
    modifier,
    move,
    offers_choice,
    op_adds_model,
    op_changes_counter,
    refund,
    remove,
    tally,
    targets_every_model,
    targets_gang,
    targets_model,
    visit_trading_post,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "note",
    [
        "Legacy source name",
        "v1|not-a-number|20|Malformed source",
        "v2|10|20|Unknown version",
    ],
)
def test_an_unrecognised_clone_note_keeps_its_plain_name(note):
    assert clone_event_details(note) == (note, None, None)


@pytest.fixture
def gang(gang_type, owner):
    return found_gang(
        "The Ashen Choir",
        gang_type,
        owner=owner,
        actor=owner,
        budget=500,
    )


@pytest.fixture
def ganger_profile(make_profile, default_pack):
    profile = make_profile("Ganger", price=50)
    add_built_in(profile, create_subtype("Ganger"))
    return profile


def _paid_for_live_assignments(gang):
    return sum(
        LedgerEntry.objects.filter(
            assignment__gang_root=gang,
            assignment__archived=False,
        ).values_list("paid", flat=True)
    )


@pytest.mark.parametrize("whole_gang", [False, True], ids=["model", "gang"])
@pytest.mark.parametrize("kind", [Action.Kind.FOUNDING, Action.Kind.TRADING_POST_VISIT])
def test_cloned_purchases_do_not_count_against_the_source_action_or_buyer(
    gang, ganger_profile, owner, whole_gang, kind
):
    fighter = hire_with_option(gang, ganger_profile, "Broker", actor=owner)
    if kind == Action.Kind.TRADING_POST_VISIT:
        visit_trading_post(gang, brought=4, actor=owner)
    source_action = gang.open_action(kind)
    sight = create_wargear("Rare sight", price=20, trade_point_price=2)
    purchase = buy(
        fighter, thing=sight, trade_points=2, action=source_action, actor=owner
    )
    assert purchase.ledger_entry.action_id == source_action.pk
    assert purchase.ledger_entry.spent_by_id == fighter.pk
    assert trade_points_spent_for(source_action) == 2
    assert trade_points_spent_by(source_action, fighter) == 2

    source_action_ids = set(
        Action.objects.filter(gang=gang).values_list("pk", flat=True)
    )
    if whole_gang:
        destination = clone_gang(gang, name="Echo", owner=owner, actor=owner)
        clone = Miniature.objects.get(membership__gang=destination, name="Broker")
        assert destination.open_action(Action.Kind.FOUNDING).pk not in source_action_ids
        assert destination.open_action(Action.Kind.TRADING_POST_VISIT) is None
    else:
        destination = gang
        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Broker II")
        assert (
            set(Action.objects.filter(gang=gang).values_list("pk", flat=True))
            == source_action_ids
        )

    copied_entries = LedgerEntry.objects.filter(assignment__miniature_root=clone)
    assert copied_entries.exists()
    assert all(
        entry.trade_points == 0
        and entry.action_id is None
        and entry.spent_by_id is None
        for entry in copied_entries
    )
    assert trade_points_spent_for(source_action) == 2
    assert trade_points_spent_by(source_action, fighter) == 2

    copied_sight = Assignment.objects.get(miniature_root=clone, wargear=sight)
    refund(copied_sight, actor=owner)
    assert trade_points_spent_for(source_action) == 2
    assert trade_points_spent_by(source_action, fighter) == 2
    gang.refresh_from_db()
    destination.refresh_from_db()
    assert_reconciled(gang)
    assert_reconciled(destination)


class TestCloningAMiniature:
    def test_clone_copies_the_current_fighter_as_an_independent_purchase(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Vex",
            actor=owner,
        )
        lasgun = create_weapon(
            "Lasgun",
            profiles=[("Standard", 0)],
            price=15,
        )
        source_weapon = give_weapon(fighter, lasgun, paid=15, actor=owner)

        with operation(gang, actor=owner) as op:
            op.edit_notes(fighter, "Keep this tactical note.")
            op.edit_lore(fighter, "Raised beneath the ash wastes.")

        gang.refresh_from_db()
        fighter.refresh_from_db()
        source_credits = gang.credits
        source_rating = gang.rating
        fighter_rating = fighter.rating
        fighter_spend = _paid_for_live_assignments(gang)
        source_default = Assignment.objects.get(
            miniature_root=fighter,
            subtype__name="Ganger",
            archived=False,
        )
        source_weapon_profile = Assignment.objects.get(
            miniature_root=fighter,
            parent=source_weapon,
            weapon_profile__isnull=False,
            archived=False,
        )

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Vex II")

        gang.refresh_from_db()
        fighter.refresh_from_db()
        clone.refresh_from_db()
        clone_weapon = Assignment.objects.get(
            miniature_root=clone,
            weapon=lasgun,
            archived=False,
        )
        clone_weapon_profile = Assignment.objects.get(
            miniature_root=clone,
            weapon_profile=source_weapon_profile.weapon_profile,
            archived=False,
        )
        clone_defaults = Assignment.objects.filter(
            miniature_root=clone,
            subtype=source_default.subtype,
            archived=False,
        )

        assert clone.pk != fighter.pk
        assert clone.membership_id != fighter.membership_id
        assert clone.name == "Vex II"
        assert clone.owner_id == fighter.owner_id
        assert clone.notes == fighter.notes
        assert clone.lore == fighter.lore
        assert clone.membership.profile_id == fighter.membership.profile_id
        assert clone.rating == fighter_rating
        assert gang.rating == source_rating + fighter_rating
        assert gang.credits == source_credits - fighter_spend

        assert clone_defaults.count() == 1
        clone_default = clone_defaults.get()
        assert clone_default.pk != source_default.pk
        assert clone_default.materialised_from_id == source_default.materialised_from_id
        assert clone_default.materialised_for_id == clone.membership_id

        assert clone_weapon.pk != source_weapon.pk
        assert clone_weapon_profile.pk != source_weapon_profile.pk
        assert clone_weapon_profile.parent_id == clone_weapon.pk
        assert clone_weapon_profile.caused_by_id == clone_weapon.pk
        assert clone_weapon_profile.parent_id != source_weapon.pk
        assert clone_weapon_profile.caused_by_id != source_weapon.pk
        clone_act = build(gang, viewer=owner)[-1]
        assert "".join(span.text for span in clone_act.spans) == "cloned Vex as Vex II"
        assert clone_act.actor == "You"
        assert clone_act.credits == -fighter_spend
        assert clone_act.rating == fighter_rating
        assert clone_act.trade_points == 0
        assert_reconciled(gang)

    def test_two_clones_in_one_operation_keep_their_own_history_totals(
        self,
        gang,
        make_profile,
        owner,
    ):
        scout = hire_with_option(
            gang,
            make_profile("Scout", price=40),
            model_name="Wisp | Ash",
            actor=owner,
        )
        champion = hire_with_option(
            gang,
            make_profile("Champion", price=90),
            model_name="Pyre",
            actor=owner,
        )

        def copied_totals(source):
            entries = LedgerEntry.objects.filter(
                assignment__miniature_root=source,
                assignment__archived=False,
            )
            return (
                sum(entries.values_list("paid", flat=True)),
                sum(entries.values_list("rating_contribution", flat=True)),
            )

        scout_credits, scout_rating = copied_totals(scout)
        champion_credits, champion_rating = copied_totals(champion)
        assert (scout_credits, scout_rating) != (
            champion_credits,
            champion_rating,
        )

        with operation(gang, actor=owner) as op:
            scout_clone = op.clone_miniature(scout, name="Wisp | Ash II")
            champion_clone = op.clone_miniature(champion, name="Pyre II")
        clone_batch = op.batch

        acts = {
            "".join(span.text for span in act.spans): act
            for act in build(gang, viewer=owner)
        }
        scout_act = acts["cloned Wisp | Ash as Wisp | Ash II"]
        champion_act = acts["cloned Pyre as Pyre II"]
        assert (scout_act.credits, scout_act.rating, scout_act.trade_points) == (
            -scout_credits,
            scout_rating,
            0,
        )
        assert (
            champion_act.credits,
            champion_act.rating,
            champion_act.trade_points,
        ) == (-champion_credits, champion_rating, 0)

        def opening_totals(clone):
            openings = LedgerEvent.objects.filter(
                batch=clone_batch,
                kind=LedgerEvent.Kind.CLONED,
                assignment__miniature_root=clone,
            )
            return (
                sum(openings.values_list("credits_delta", flat=True)),
                sum(openings.values_list("rating_delta", flat=True)),
                sum(openings.values_list("trade_points_delta", flat=True)),
            )

        assert opening_totals(scout_clone) == (
            -scout_act.credits,
            scout_act.rating,
            -scout_act.trade_points,
        )
        assert opening_totals(champion_clone) == (
            -champion_act.credits,
            champion_act.rating,
            -champion_act.trade_points,
        )

        standalone = LedgerEvent.objects.filter(
            batch=clone_batch,
            kind=LedgerEvent.Kind.CLONED,
            assignment__isnull=True,
            miniature__in=(scout_clone, champion_clone),
        )
        assert standalone.count() == 2
        assert all(
            (event.credits_delta, event.rating_delta, event.trade_points_delta)
            == (0, 0, 0)
            for event in standalone
        )
        gang.refresh_from_db()
        assert_reconciled(gang)

    @pytest.mark.parametrize("destination", ["fighter", "stash"])
    def test_a_moved_default_becomes_a_guard_instead_of_live_clone_kit(
        self,
        destination,
        gang,
        ganger_profile,
        make_profile,
        owner,
    ):
        respirator = create_wargear("Respirator")
        member = add_built_in(ganger_profile, respirator)
        source = hire_with_option(
            gang,
            ganger_profile,
            model_name="Cinder",
            actor=owner,
        )
        source_copy = Assignment.objects.get(
            materialised_from=member,
            materialised_for=source.membership,
            archived=False,
        )
        if destination == "fighter":
            recipient = hire_with_option(
                gang,
                make_profile("Lookout", price=30),
                model_name="Watch",
                actor=owner,
            )
        else:
            recipient = gang.stash

        move(source_copy, recipient, actor=owner)

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(source, name="Cinder II")

        source_copy.refresh_from_db()
        guard = Assignment.objects.get(
            materialised_from=member,
            materialised_for=clone.membership,
        )
        assert source_copy.archived is False
        if destination == "fighter":
            assert source_copy.miniature_root_id == recipient.pk
        else:
            assert source_copy.stash_root_id == recipient.pk
        assert guard.archived is True
        assert guard.miniature_root_id == clone.pk
        assert not Assignment.objects.filter(
            materialised_from=member,
            materialised_for=clone.membership,
            archived=False,
        ).exists()
        assert (
            Assignment.objects.filter(
                gang_root=gang,
                wargear=respirator,
                archived=False,
            ).count()
            == 1
        )

        with operation(gang, actor=owner) as op:
            outcome = op.reconcile_defaults(clone.membership)

        assert not any(
            assignment.materialised_from_id == member.pk
            for assignment in outcome.created
        )
        assert (
            Assignment.objects.filter(
                materialised_from=member,
                materialised_for=clone.membership,
            ).count()
            == 1
        )
        guard.refresh_from_db()
        assert guard.archived is True
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_clone_does_not_spend_the_sources_trade_points_again(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Broker",
            actor=owner,
        )
        rare_sight = create_wargear("Rare sight", price=20, trade_point_price=2)
        assign(
            rare_sight,
            miniature=fighter,
            paid=20,
            trade_points=2,
            actor=owner,
        )
        source_entries = LedgerEntry.objects.filter(
            assignment__miniature_root=fighter,
            assignment__archived=False,
        )
        copied_credits = sum(source_entries.values_list("paid", flat=True))
        copied_rating = sum(
            source_entries.values_list("rating_contribution", flat=True)
        )
        assert copied_credits > 0
        assert copied_rating > 0

        visit_trading_post(gang, brought=4, actor=owner)
        gang.refresh_from_db()
        assert gang.trade_points_left == 4

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Broker II")

        gang.refresh_from_db()
        assert gang.trade_points_left == 4
        assert (
            sum(
                LedgerEntry.objects.filter(
                    assignment__miniature_root=clone,
                    assignment__archived=False,
                ).values_list("trade_points", flat=True)
            )
            == 0
        )
        clone_act = build(gang, viewer=owner)[-1]
        assert "".join(span.text for span in clone_act.spans) == (
            "cloned Broker as Broker II"
        )
        assert clone_act.credits == -copied_credits
        assert clone_act.rating == copied_rating
        assert clone_act.trade_points == 0
        assert clone_act.category == "money"

        cloned_sight = Assignment.objects.get(
            miniature_root=clone,
            wargear=rare_sight,
            archived=False,
        )
        remove(cloned_sight, actor=owner)
        historical_clone_act = next(
            act
            for act in build(gang, viewer=owner)
            if "".join(span.text for span in act.spans) == "cloned Broker as Broker II"
        )
        assert historical_clone_act.credits == -copied_credits
        assert historical_clone_act.rating == copied_rating
        assert historical_clone_act.trade_points == 0
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_limited_campaign_log_keeps_the_whole_clone_act(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        campaign = Campaign.objects.create(
            name="Dust Falls",
            owner=owner,
            budget=500,
        )
        with operation(gang, actor=owner) as op:
            op.join_campaign(campaign)
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Quartermaster",
            actor=owner,
        )
        for number in range(6):
            assign(
                create_wargear(f"Pack {number}"),
                miniature=fighter,
                paid=5,
                actor=owner,
            )
        history_size = campaign_history_size(campaign)
        with operation(gang, actor=owner) as op:
            op.clone_miniature(fighter, name="Quartermaster II")

        expected = next(
            act
            for act in build(gang, viewer=owner)
            if "cloned Quartermaster as Quartermaster II"
            == "".join(span.text for span in act.spans)
        )
        limited = campaign_history(campaign, viewer=owner, limit=5)
        actual = next(
            act
            for act in limited
            if "cloned Quartermaster as Quartermaster II"
            == "".join(span.text for span in act.spans)
        )

        assert len(limited) == 5
        assert campaign_history_size(campaign) == history_size + 1
        assert actual.credits == expected.credits
        assert actual.rating == expected.rating
        assert actual.trade_points == expected.trade_points == 0

    def test_clone_keeps_a_nested_gang_choice_as_its_live_anchor(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        doctrine = create_slot_type("Doctrine")
        hold_fast = create_pickable("Hold fast", doctrine)
        doctrines = create_picklist("Doctrines", doctrine, members=[hold_fast])
        question = create_slot("Doctrine", doctrine, doctrines)
        gang_question = create_wargear("Gang counsel")
        modifier(
            "The gang counsel asks every model for a doctrine",
            targets_every_model(),
            ef_adds(question),
            carried_by=gang_question,
        )
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Adept",
            actor=owner,
        )
        with operation(gang, actor=owner) as op:
            counsel = op.assign(create_wargear("Council chamber"), gang=gang)
            anchor = op.assign(gang_question, parent=counsel, caused_by=counsel)
            source_pick = op.choose(
                anchor,
                hold_fast,
                slot=question,
                miniature=fighter,
            )

        assert anchor.parent_id == counsel.pk
        assert anchor.gang_id is None
        assert anchor.gang_root_id == gang.pk
        assert source_pick.caused_by_id == anchor.pk
        assert source_pick.chosen_for_id == anchor.pk

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Adept II")

        cloned_pick = Assignment.objects.get(
            miniature_root=clone,
            pickable=hold_fast,
            archived=False,
        )
        assert cloned_pick.pk != source_pick.pk
        assert cloned_pick.caused_by_id == anchor.pk
        assert cloned_pick.chosen_for_id == anchor.pk
        card = build_card(clone)
        computed = compute(
            card,
            build_modifier_index([node.assignable for node in card.all_nodes()]),
        )
        cloned_choice = next(
            choice for choice in computed.choices if choice.kind_label == "Doctrine"
        )
        assert cloned_choice.is_resolved
        assert cloned_choice.chosen_name == "Hold fast"
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_clone_remaps_a_gang_answer_after_its_offer_was_rewritten(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        creed = create_affiliation("Ash creed")
        omens = create_counter("Favour")
        modifier(
            "The creed earns favour",
            targets_gang(),
            op_changes_counter(omens, "add", 3),
            carried_by=creed,
        )
        offer = offers_choice(
            type(creed),
            label="Creed",
            will_be_assigned_to="gang",
        )
        offering = modifier(
            "A Ganger chooses the gang's creed",
            targets_model(),
            offer,
            carried_by=ganger_profile,
        )
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Envoy",
            actor=owner,
        )
        with operation(gang, actor=owner) as op:
            source_answer = op.choose(fighter.membership, creed, offer=offer)
        source_counter = Assignment.objects.get(
            gang=gang,
            counter=omens,
            archived=False,
        )
        assert CounterValue.objects.get(assignment=source_counter).value == 3

        assert source_answer.gang_id == gang.pk
        assert source_answer.caused_by_id == fighter.membership_id
        assert source_answer.chosen_for_offer_id == offer.pk
        from n26.library.authoring import recompose_modifier

        recompose_modifier(
            offering,
            "A Ganger chooses the gang's creed",
            targets_model(),
            offers_choice(
                type(creed),
                label="Creed",
                will_be_assigned_to="gang",
            ),
        )
        source_answer.refresh_from_db()
        assert source_answer.chosen_for_offer_id is None
        source_card = build_card(fighter)
        source_computed = compute(
            source_card,
            build_modifier_index([node.assignable for node in source_card.all_nodes()]),
        )
        source_choice = next(
            choice for choice in source_computed.choices if choice.kind_label == "Creed"
        )
        assert source_choice.is_resolved
        assert source_choice.chosen_name == "Ash creed"

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Envoy II")

        cloned_answer = Assignment.objects.exclude(pk=source_answer.pk).get(
            gang=gang,
            affiliation=creed,
            caused_by=clone.membership,
            archived=False,
        )
        assert cloned_answer.chosen_for_offer_id is None
        assert cloned_answer.caused_by_id != fighter.membership_id
        assert (
            Assignment.objects.filter(
                gang=gang,
                counter=omens,
                archived=False,
            ).count()
            == 1
        )
        assert CounterValue.objects.get(assignment=source_counter).value == 3
        card = build_card(clone)
        computed = compute(
            card,
            build_modifier_index([node.assignable for node in card.all_nodes()]),
        )
        cloned_choice = next(
            choice for choice in computed.choices if choice.kind_label == "Creed"
        )
        assert cloned_choice.is_resolved
        assert cloned_choice.chosen_name == "Ash creed"
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_clone_keeps_the_live_built_in_of_a_gang_answer(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        creed = create_subtype("Ash creed")
        relic = create_wargear("Ash relic")
        member = add_built_in(creed, relic)
        offer = offers_choice(
            type(creed),
            label="Creed",
            will_be_assigned_to="gang",
        )
        modifier(
            "A Ganger chooses the gang's creed",
            targets_model(),
            offer,
            carried_by=ganger_profile,
        )
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Envoy",
            actor=owner,
        )
        with operation(gang, actor=owner) as op:
            source_answer = op.choose(fighter.membership, creed, offer=offer)
            outcome = op.reconcile_defaults(source_answer, gang=gang)
        source_default = outcome.created[0]

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Envoy II")

        cloned_answer = Assignment.objects.get(
            gang=gang,
            subtype=creed,
            caused_by=clone.membership,
            archived=False,
        )
        cloned_default = Assignment.objects.get(
            gang=gang,
            wargear=relic,
            materialised_from=member,
            materialised_for=cloned_answer,
        )
        assert cloned_default.pk != source_default.pk
        assert cloned_default.caused_by_id == cloned_answer.pk
        assert cloned_default.archived is False

        remove(fighter.membership, actor=owner)

        source_default.refresh_from_db()
        cloned_answer.refresh_from_db()
        cloned_default.refresh_from_db()
        assert source_default.archived is True
        assert cloned_answer.archived is False
        assert cloned_default.archived is False
        with operation(gang, actor=owner) as op:
            outcome = op.reconcile_defaults(cloned_answer, gang=gang)
        assert outcome.created == []
        assert (
            Assignment.objects.filter(
                materialised_from=member,
                materialised_for=cloned_answer,
            ).count()
            == 1
        )
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_clone_rolls_back_when_the_gang_cannot_afford_the_fighter(
        self,
        gang_type,
        ganger_profile,
        owner,
    ):
        gang = found_gang(
            "The Cinder Kin",
            gang_type,
            owner=owner,
            actor=owner,
            budget=75,
        )
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Cinder",
            actor=owner,
        )
        gang.refresh_from_db()
        miniature_ids = set(
            Miniature.objects.filter(membership__gang=gang).values_list("pk", flat=True)
        )
        assignment_ids = set(
            Assignment.objects.filter(gang_root=gang).values_list("pk", flat=True)
        )
        ledger_entry_ids = set(
            LedgerEntry.objects.filter(assignment__gang_root=gang).values_list(
                "pk", flat=True
            )
        )
        credits = gang.credits
        rating = gang.rating

        with pytest.raises(NotEnoughCredits):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(fighter, name="Cinder II")

        gang.refresh_from_db()
        assert (
            set(
                Miniature.objects.filter(membership__gang=gang).values_list(
                    "pk", flat=True
                )
            )
            == miniature_ids
        )
        assert (
            set(Assignment.objects.filter(gang_root=gang).values_list("pk", flat=True))
            == assignment_ids
        )
        assert (
            set(
                LedgerEntry.objects.filter(assignment__gang_root=gang).values_list(
                    "pk", flat=True
                )
            )
            == ledger_entry_ids
        )
        assert gang.credits == credits
        assert gang.rating == rating
        assert_reconciled(gang)

    def test_a_stale_model_cannot_be_cloned_after_its_membership_is_removed(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Last Light",
            actor=owner,
        )
        stale = Miniature.objects.select_related("membership").get(pk=fighter.pk)
        fresh = Miniature.objects.select_related("membership").get(pk=fighter.pk)
        remove(fresh.membership, actor=owner)
        fresh.membership.refresh_from_db()
        assert stale.membership.archived is False
        assert fresh.membership.archived is True
        before = set(
            Miniature.objects.filter(membership__gang=gang).values_list("pk", flat=True)
        )

        with pytest.raises(Refusal, match=r"That model can no longer be cloned\."):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(stale, name="False Light")

        assert (
            set(
                Miniature.objects.filter(membership__gang=gang).values_list(
                    "pk", flat=True
                )
            )
            == before
        )
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_an_archived_default_still_blocks_regranting_after_the_clone(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Ember",
            actor=owner,
        )
        source_guard = Assignment.objects.get(
            miniature_root=fighter,
            subtype__name="Ganger",
            materialised_for=fighter.membership,
        )
        remove(source_guard, actor=owner)

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Ember II")

        clone_guard = Assignment.objects.get(
            miniature_root=clone,
            materialised_from_id=source_guard.materialised_from_id,
            materialised_for=clone.membership,
        )
        assert clone_guard.pk != source_guard.pk
        assert clone_guard.archived is True
        assert not Assignment.objects.filter(
            miniature_root=clone,
            subtype=source_guard.subtype,
            archived=False,
        ).exists()

        with operation(gang, actor=owner) as op:
            outcome = op.reconcile_defaults(clone.membership)

        guards = Assignment.objects.filter(
            miniature_root=clone,
            materialised_from_id=source_guard.materialised_from_id,
            materialised_for=clone.membership,
        )
        assert outcome.created == []
        assert guards.count() == 1
        assert guards.get().archived is True
        assert not Assignment.objects.filter(
            miniature_root=clone,
            subtype=source_guard.subtype,
            archived=False,
        ).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_an_archived_nested_default_is_rehosted_without_its_old_parent(
        self,
        gang,
        ganger_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Grenadier",
            actor=owner,
        )
        launcher = create_weapon(
            "Grenade launcher",
            profiles=[("Frag", 0), ("Smoke", 10)],
            price=30,
        )
        source_launcher = give_weapon(fighter, launcher, paid=30, actor=owner)
        smoke = launcher.profiles.get(name="Smoke")
        member = add_built_in(ganger_profile, smoke)
        with operation(gang, actor=owner) as op:
            op.reconcile_defaults(fighter.membership)
        source_smoke = Assignment.objects.get(
            materialised_from=member,
            materialised_for=fighter.membership,
            weapon_profile=smoke,
        )
        assert source_smoke.parent_id == source_launcher.pk

        remove(source_launcher, actor=owner)
        source_launcher.refresh_from_db()
        source_smoke.refresh_from_db()
        assert source_launcher.archived is True
        assert source_smoke.archived is True

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Grenadier II")

        guard = Assignment.objects.get(
            materialised_from=member,
            materialised_for=clone.membership,
            weapon_profile=smoke,
        )
        assert guard.archived is True
        assert guard.parent_id is None
        assert guard.miniature_root_id == clone.pk
        assert not Assignment.objects.filter(
            miniature_root=clone,
            weapon_profile=smoke,
            archived=False,
        ).exists()

        cloned_launcher = give_weapon(clone, launcher, paid=30, actor=owner)
        with operation(gang, actor=owner) as op:
            outcome = op.reconcile_defaults(clone.membership)

        assert not any(
            assignment.weapon_profile_id == smoke.pk for assignment in outcome.created
        )
        assert not Assignment.objects.filter(
            miniature_root=clone,
            parent=cloned_launcher,
            weapon_profile=smoke,
            archived=False,
        ).exists()
        assert (
            Assignment.objects.filter(
                materialised_from=member,
                materialised_for=clone.membership,
            ).count()
            == 1
        )
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_model_that_brought_a_pet_is_cloned_with_the_pet(
        self,
        gang,
        ganger_profile,
        make_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Handler",
            actor=owner,
        )
        mastiff = make_profile("Cyber-mastiff", price=100)
        pet_wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            targets_model(),
            op_adds_model(mastiff),
            carried_by=pet_wargear,
        )
        source_wargear = assign(
            pet_wargear,
            miniature=fighter,
            paid=100,
            actor=owner,
        )
        source_pet = Miniature.objects.get(
            membership__caused_by=source_wargear,
        )
        pet_collar = create_wargear("Spiked collar")
        assign(pet_collar, miniature=source_pet, paid=15, actor=owner)

        with operation(gang, actor=owner) as op:
            clone = op.clone_miniature(fighter, name="Handler II")

        cloned_wargear = Assignment.objects.get(
            miniature_root=clone,
            wargear=pet_wargear,
            archived=False,
        )
        cloned_pet = Miniature.objects.get(
            membership__caused_by=cloned_wargear,
        )
        assert cloned_pet.pk != source_pet.pk
        assert cloned_pet.owned_by == clone
        assert (
            Assignment.objects.filter(
                miniature_root=cloned_pet,
                wargear=pet_collar,
                archived=False,
            ).count()
            == 1
        )
        assert Miniature.objects.filter(membership__gang=gang).count() == 4
        assert_reconciled(gang)

    def test_a_pet_cannot_be_cloned_without_the_model_that_brought_it(
        self,
        gang,
        ganger_profile,
        make_profile,
        owner,
    ):
        fighter = hire_with_option(
            gang,
            ganger_profile,
            model_name="Handler",
            actor=owner,
        )
        mastiff = make_profile("Cyber-mastiff", price=100)
        pet_wargear = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "Cyber-mastiff wargear brings a pet",
            targets_model(),
            op_adds_model(mastiff),
            carried_by=pet_wargear,
        )
        source_wargear = assign(
            pet_wargear,
            miniature=fighter,
            paid=100,
            actor=owner,
        )
        pet = Miniature.objects.get(membership__caused_by=source_wargear)
        before = set(
            Miniature.objects.filter(membership__gang=gang).values_list("pk", flat=True)
        )

        with pytest.raises(
            Refusal,
            match=(
                "Cyber-mastiff cannot be cloned on its own. "
                "Clone Handler to include both models."
            ),
        ):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(pet, name="Cyber-mastiff II")

        assert (
            set(
                Miniature.objects.filter(membership__gang=gang).values_list(
                    "pk", flat=True
                )
            )
            == before
        )
        assert_reconciled(gang)

    def test_a_gang_granted_model_can_only_be_copied_with_the_gang(
        self,
        gang,
        make_profile,
        owner,
    ):
        delegate = make_profile("Guild envoy", price=100)
        alliance = create_wargear("Guild alliance")
        modifier(
            "The alliance brings a Guild envoy",
            targets_gang(),
            op_adds_model(delegate),
            carried_by=alliance,
        )
        pact = assign(alliance, gang=gang, paid=100, actor=owner)
        envoy = Miniature.objects.get(membership__caused_by=pact)
        before = set(
            Miniature.objects.filter(membership__gang=gang).values_list("pk", flat=True)
        )

        with pytest.raises(
            Refusal,
            match=(
                "Guild envoy cannot be cloned on its own. "
                "Clone the gang to include this model."
            ),
        ):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(envoy, name="Second envoy")

        assert (
            set(
                Miniature.objects.filter(membership__gang=gang).values_list(
                    "pk", flat=True
                )
            )
            == before
        )
        assert_reconciled(gang)


class TestCloningAGang:
    def test_a_stale_gang_cannot_be_cloned_after_it_is_archived(
        self,
        gang,
        owner,
    ):
        stale = Gang.objects.get(pk=gang.pk)
        fresh = Gang.objects.get(pk=gang.pk)
        fresh.archive()
        assert stale.archived is False
        assert fresh.archived is True
        before = set(Gang.objects.values_list("pk", flat=True))

        with pytest.raises(Refusal, match=r"That gang can no longer be cloned\."):
            clone_gang(
                stale,
                name="The Ashen Choir Echo",
                owner=owner,
                actor=owner,
            )

        assert set(Gang.objects.values_list("pk", flat=True)) == before

    def test_clone_preserves_live_kit_and_descendants_on_a_departed_model(
        self,
        gang,
        ganger_profile,
        make_profile,
        owner,
    ):
        handler = hire_with_option(
            gang,
            ganger_profile,
            model_name="Handler",
            actor=owner,
        )
        mastiff_profile = make_profile("Cyber-mastiff", price=100)
        mastiff_token = create_wargear("Cyber-mastiff (pet)")
        modifier(
            "The token brings a Cyber-mastiff",
            targets_model(),
            op_adds_model(mastiff_profile),
            carried_by=mastiff_token,
        )
        token = assign(
            mastiff_token,
            miniature=handler,
            paid=100,
            actor=owner,
        )
        mastiff = Miniature.objects.get(membership__caused_by=token)

        rat_profile = make_profile("Giant rat", price=25)
        brood_collar = create_wargear("Brood collar")
        modifier(
            "The collar brings a Giant rat",
            targets_model(),
            op_adds_model(rat_profile),
            carried_by=brood_collar,
        )
        collar = assign(
            brood_collar,
            miniature=mastiff,
            paid=15,
            actor=owner,
        )
        rat = Miniature.objects.get(membership__caused_by=collar)

        remove(token, actor=owner)
        collar.refresh_from_db()
        mastiff.membership.refresh_from_db()
        rat.membership.refresh_from_db()
        assert mastiff.membership.archived is True
        assert collar.archived is False
        assert rat.membership.archived is False
        assert rat.owned_by == mastiff

        with pytest.raises(
            Refusal,
            match=(
                "Giant rat cannot be cloned on its own. "
                "Clone the gang to include this model."
            ),
        ):
            with operation(gang, actor=owner) as op:
                op.clone_miniature(rat, name="Second rat")

        gang.refresh_from_db()
        source_credits = gang.credits
        source_rating = gang.rating
        clone = clone_gang(
            gang,
            name="The Ashen Choir Echo",
            owner=owner,
            actor=owner,
        )

        hidden_mastiff = Miniature.objects.get(
            membership__gang=clone,
            membership__archived=True,
            name="Cyber-mastiff",
        )
        cloned_collar = Assignment.objects.get(
            gang_root=clone,
            miniature_root=hidden_mastiff,
            wargear=brood_collar,
            archived=False,
        )
        cloned_rat = Miniature.objects.get(
            membership__gang=clone,
            membership__archived=False,
            name="Giant rat",
        )
        clone.refresh_from_db()
        cloned_collar.ledger_entry.refresh_from_db()

        assert hidden_mastiff.membership.archived is True
        assert cloned_collar.ledger_entry.paid == 15
        assert cloned_rat.membership.caused_by_id == cloned_collar.pk
        assert cloned_rat.owned_by == hidden_mastiff
        assert clone.credits == source_credits
        assert clone.rating == source_rating
        assert_reconciled(gang)
        assert_reconciled(clone)

    def test_clone_copies_the_live_roster_and_stash_with_a_derived_budget(
        self,
        gang_type,
        ganger_profile,
        owner,
    ):
        source = found_gang(
            "The Ember Court",
            gang_type,
            owner=owner,
            actor=owner,
            budget=300,
        )
        fighter = hire_with_option(
            source,
            ganger_profile,
            model_name="Pyre",
            actor=owner,
        )
        lasgun = create_weapon(
            "Lasgun",
            profiles=[("Standard", 0)],
            price=15,
        )
        source_weapon = give_weapon(fighter, lasgun, paid=15, actor=owner)
        ammo_crate = create_wargear("Ammo crate", price=25)
        source_stash_item = assign(
            ammo_crate,
            stash=source.stash,
            paid=25,
            actor=owner,
        )
        discarded_item = create_wargear("Spent charge pack", price=20)
        discarded_assignment = assign(
            discarded_item,
            miniature=fighter,
            paid=20,
            actor=owner,
        )
        remove(discarded_assignment, actor=owner)
        campaign = Campaign.objects.create(
            name="Ash Wastes Run",
            owner=owner,
            budget=500,
        )
        with operation(source, actor=owner) as op:
            op.join_campaign(campaign)
        visit_trading_post(source, brought=4, actor=owner)

        source.refresh_from_db()
        source.stash.refresh_from_db()
        fighter.refresh_from_db()
        source_assignment_ids = set(
            Assignment.objects.filter(gang_root=source).values_list("pk", flat=True)
        )
        source_miniature_ids = set(
            Miniature.objects.filter(membership__gang=source).values_list(
                "pk", flat=True
            )
        )
        source_credits = source.credits
        source_rating = source.rating
        source_stash_rating = source.stash.rating
        source_starting_credits = source.starting_credits
        copied_spend = _paid_for_live_assignments(source)
        assert source.visiting_trading_post is True
        assert source.trade_points_left == 4
        assert CampaignMembership.objects.filter(
            campaign=campaign,
            gang=source,
            left__isnull=True,
        ).exists()

        clone = clone_gang(
            source,
            name="The Ember Court Echo",
            owner=owner,
            actor=owner,
        )

        source.refresh_from_db()
        source.stash.refresh_from_db()
        clone = Gang.objects.select_related("stash", "founding").get(pk=clone.pk)
        cloned_fighter = Miniature.objects.get(
            membership__gang=clone,
            membership__archived=False,
            name=fighter.name,
        )
        cloned_weapon = Assignment.objects.get(
            miniature_root=cloned_fighter,
            weapon=lasgun,
            archived=False,
        )
        cloned_stash_item = Assignment.objects.get(
            stash=clone.stash,
            wargear=ammo_crate,
            archived=False,
        )

        assert clone.pk != source.pk
        assert clone.founding_id != source.founding_id
        assert clone.stash.pk != source.stash.pk
        assert clone.name == "The Ember Court Echo"
        assert clone.owner_id == owner.pk
        assert clone.gang_type_id == source.gang_type_id
        assert clone.credits == source_credits
        assert clone.rating == source_rating
        assert clone.stash.rating == source_stash_rating
        assert clone.starting_credits == source_credits + copied_spend
        assert clone.starting_credits != source_starting_credits
        assert clone.visiting_trading_post is False
        founding = clone.open_action(Action.Kind.FOUNDING)
        assert founding is not None
        assert founding.trade_points is None
        assert founding.pk != source.open_action(Action.Kind.FOUNDING).pk
        assert Action.objects.filter(gang=clone).count() == 1
        assert clone.trade_points_left is None
        assert not CampaignMembership.objects.filter(gang=clone).exists()

        assert cloned_fighter.pk not in source_miniature_ids
        assert cloned_fighter.membership.profile_id == fighter.membership.profile_id
        assert cloned_fighter.rating == fighter.rating
        assert cloned_weapon.pk != source_weapon.pk
        assert cloned_stash_item.pk != source_stash_item.pk
        assert cloned_stash_item.stash_id == clone.stash.pk
        assert not Assignment.objects.filter(
            gang_root=clone,
            wargear=discarded_item,
        ).exists()
        assert not source_assignment_ids.intersection(
            Assignment.objects.filter(gang_root=clone).values_list("pk", flat=True)
        )

        assert source.credits == source_credits
        assert source.rating == source_rating
        assert source.stash.rating == source_stash_rating
        assert (
            set(
                Assignment.objects.filter(gang_root=source).values_list("pk", flat=True)
            )
            == source_assignment_ids
        )
        clone_history = build(clone, viewer=owner)
        assert len(clone_history) == 2
        assert "".join(span.text for span in clone_history[0].spans) == (
            "cloned the gang from The Ember Court"
        )
        assert "".join(span.text for span in clone_history[1].spans) == (
            "started the Found and equip gang action"
        )
        assert_reconciled(source)
        assert_reconciled(clone)

    def test_clone_remaps_counter_stats_card_sets_and_print_configs(
        self,
        gang_type,
        ganger_profile,
        make_statline,
        owner,
    ):
        make_statline(
            ganger_profile,
            movement=5,
            weapon_skill=4,
            toughness=3,
        )
        source = found_gang(
            "The Lantern Guard",
            gang_type,
            owner=owner,
            actor=owner,
            budget=300,
        )
        fighter = hire_with_option(
            source,
            ganger_profile,
            model_name="Lux",
            actor=owner,
        )
        lasgun = create_weapon(
            "Lasgun",
            profiles=[("Standard", 0)],
            price=15,
        )
        source_weapon = give_weapon(fighter, lasgun, paid=15, actor=owner)
        kills = create_counter("Kill Count")
        source_counter = assign(kills, miniature=fighter, actor=owner)
        tally(source_counter, +4, actor=owner)

        movement = ganger_profile.statline_type.stats.get(stat__field_name="movement")
        with operation(source, actor=owner) as op:
            op.set_stats(fighter, [(movement, "6", 'Movement 5" → 6"')])

        source_set = create_assignment_set(
            fighter,
            "Patrol kit",
            [source_weapon],
        )
        source_config = PrintConfig.objects.create(
            gang=source,
            name="Patrol cards",
            include_header=False,
            include_stash=False,
            include_notes=False,
        )
        source_config.miniatures.set([fighter])
        source_config.assignments.set([source_weapon])
        source_counter_value = CounterValue.objects.get(assignment=source_counter)
        source_override = StatOverride.objects.get(
            miniature=fighter,
            statline_type_stat=movement,
        )

        clone = clone_gang(
            source,
            name="The Lantern Guard Echo",
            owner=owner,
            actor=owner,
        )

        cloned_fighter = Miniature.objects.get(
            membership__gang=clone,
            name=fighter.name,
        )
        cloned_weapon = Assignment.objects.get(
            miniature_root=cloned_fighter,
            weapon=lasgun,
            archived=False,
        )
        cloned_counter = Assignment.objects.get(
            miniature_root=cloned_fighter,
            counter=kills,
            archived=False,
        )
        cloned_counter_value = CounterValue.objects.get(assignment=cloned_counter)
        cloned_override = StatOverride.objects.get(
            miniature=cloned_fighter,
            statline_type_stat=movement,
        )
        cloned_set = AssignmentSet.objects.get(
            miniature=cloned_fighter,
            name=source_set.name,
        )
        cloned_config = PrintConfig.objects.get(
            gang=clone,
            name=source_config.name,
        )

        assert cloned_counter_value.pk != source_counter_value.pk
        assert cloned_counter_value.assignment_id == cloned_counter.pk
        assert cloned_counter_value.assignment_id != source_counter.pk
        assert cloned_counter_value.value == source_counter_value.value == 4

        assert cloned_override.pk != source_override.pk
        assert cloned_override.miniature_id == cloned_fighter.pk
        assert cloned_override.miniature_id != fighter.pk
        assert cloned_override.value == source_override.value

        assert cloned_set.pk != source_set.pk
        assert cloned_set.miniature_id == cloned_fighter.pk
        assert set(cloned_set.assignments.values_list("pk", flat=True)) == {
            cloned_weapon.pk
        }
        assert set(source_set.assignments.values_list("pk", flat=True)) == {
            source_weapon.pk
        }

        assert cloned_config.pk != source_config.pk
        assert cloned_config.include_header is False
        assert cloned_config.include_stash is False
        assert cloned_config.include_notes is False
        assert set(cloned_config.miniatures.values_list("pk", flat=True)) == {
            cloned_fighter.pk
        }
        assert set(cloned_config.assignments.values_list("pk", flat=True)) == {
            cloned_weapon.pk
        }
        assert set(source_config.miniatures.values_list("pk", flat=True)) == {
            fighter.pk
        }
        assert set(source_config.assignments.values_list("pk", flat=True)) == {
            source_weapon.pk
        }
        source.refresh_from_db()
        clone.refresh_from_db()
        assert_reconciled(source)
        assert_reconciled(clone)
