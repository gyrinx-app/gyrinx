"""Placed skill and power selection shares keyed native and JSON commands."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.http import QueryDict
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import Assignment, Gang, ModelChoiceReceipt, Reason
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import Power, Skill
from n26.tests.sandbox.actions import (
    assign,
    create_category,
    create_collection,
    create_power,
    create_skill,
    create_subtype,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places,
    section_of,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def choices(gang_type, make_profile):
    actor = User.objects.create_user("skills-player")
    gang = found_gang("Skill test gang", gang_type, owner=actor, budget=1000)
    agility = create_category("Skills", "Agility")
    powers = create_category("Powers", "Wyrd Powers")
    catfall = create_skill("Catfall", category=agility)
    dodge = create_skill("Dodge", category=agility)
    terrify = create_power("Terrify", "Double", category=powers, price=30)
    collection = create_collection("Skills & Powers", contains=[Skill, Power])
    primary = section_of(collection, "Primary", 0)
    secondary = section_of(collection, "Secondary", 1)
    section_of(collection, "Other", 9, is_default=True)
    profile = make_profile("Ganger", price=50)
    for category, section in [(agility, primary), (powers, secondary)]:
        modifier(
            f"Place {category}",
            targets_model(),
            places(category, section),
            carried_by=profile,
        )
    model = hire_with_option(gang, profile, "Vex")
    return SimpleNamespace(
        actor=actor,
        gang=gang,
        model=model,
        profile=profile,
        agility=agility,
        powers=powers,
        catfall=catfall,
        dodge=dodge,
        terrify=terrify,
        collection=collection,
        primary=primary,
        secondary=secondary,
    )


def url(choices, *, command=False):
    return reverse(
        "n26-skills-command" if command else "n26-skills", args=[choices.model.pk]
    )


def key(thing):
    return f"{thing._meta.label_lower}:{thing.pk}"


def page(client, choices):
    return client.get(url(choices)).context["skills_props"]


def submission(client, choices, thing):
    return {
        **page(client, choices)["values"],
        "thing": key(thing),
        "thing_label": str(thing),
    }


def open_offer(choices, *, power=False):
    leader = create_subtype("Wyrd" if power else "Leader")
    modifier(
        "Starting selection",
        targets_model(),
        offers_choice(
            Power if power else Skill,
            from_section=choices.secondary if power else choices.primary,
        ),
        carried_by=leader,
    )
    return assign(leader, miniature=choices.model)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("power", [False, True])
def test_both_adapters_select_a_placed_skill_or_power_without_spending(
    client, choices, command, power
):
    client.force_login(choices.actor)
    thing = choices.terrify if power else choices.catfall
    before = choices.gang.credits
    response = client.post(
        url(choices, command=command), submission(client, choices, thing)
    )
    assert response.status_code == (200 if command else 302)
    destination = response.json()["nextUrl"] if command else response.url
    assert destination == reverse("n26-edit-fighter", args=[choices.model.pk])
    selected = Assignment.objects.get(
        miniature_root=choices.model, **{"power" if power else "skill": thing}
    )
    assert selected.ledger_entry.paid == 0
    assert selected.ledger_entry.reason == Reason.REWARD
    assert selected.ledger_entry.rating_contribution == (30 if power else 0)
    assert selected.caused_by_id is None
    choices.gang.refresh_from_db()
    assert choices.gang.credits == before
    assert ModelChoiceReceipt.objects.count() == 1
    assert_reconciled(choices.gang)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("power", [False, True])
def test_a_matching_starting_offer_is_settled_and_replayed_before_current_offers(
    client, choices, command, power
):
    anchor = open_offer(choices, power=power)
    thing = choices.terrify if power else choices.catfall
    client.force_login(choices.actor)
    values = submission(client, choices, thing)
    with patch("n26.analytics.record") as recorded:
        assert client.post(url(choices, command=command), values).status_code == (
            200 if command else 302
        )
        assert client.post(url(choices, command=command), values).status_code == (
            200 if command else 302
        )
    assert recorded.call_count == 1
    selected = Assignment.objects.get(
        miniature_root=choices.model, **{"power" if power else "skill": thing}
    )
    assert selected.caused_by_id == anchor.pk
    assert selected.chosen_for_offer_id is not None
    assert ModelChoiceReceipt.objects.count() == 1
    assert_reconciled(choices.gang)


@pytest.mark.parametrize("command", [False, True])
def test_known_content_is_refused_without_turning_it_into_a_replay(
    client, choices, command
):
    with operation(choices.gang, actor=choices.actor) as op:
        op.select(choices.model, choices.catfall)
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    response = client.post(url(choices, command=command), values)
    assert response.status_code == 422
    errors = (
        response.json()["errors"]
        if command
        else response.context["skills_props"]["errors"]
    )
    assert errors["thing"] == ["Vex already has Catfall."]
    assert not ModelChoiceReceipt.objects.exists()
    assert (
        Assignment.objects.filter(
            miniature_root=choices.model, skill=choices.catfall
        ).count()
        == 1
    )
    assert_reconciled(choices.gang)


@pytest.mark.parametrize("command", [False, True])
def test_replay_survives_removed_model_and_offer(client, choices, command):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    assert client.post(url(choices, command=command), values).status_code == (
        200 if command else 302
    )
    with operation(choices.gang, actor=choices.actor) as op:
        op.remove(choices.model.membership)
    response = client.post(url(choices, command=command), values)
    assert response.status_code == (200 if command else 302)
    assert (response.json()["nextUrl"] if command else response.url) == reverse(
        "n26-gang", args=[choices.gang.pk]
    )
    assert ModelChoiceReceipt.objects.count() == 1
    assert_reconciled(choices.gang)


def test_replay_survives_removed_collection_and_queues_success_once(client, choices):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    client.post(url(choices, command=True), values)
    from n26.library.authoring import delete_modifier

    for attached in list(choices.profile.modifiers.all()):
        delete_modifier(attached)
    choices.collection.delete()
    assert client.post(url(choices, command=True), values).status_code == 200
    messages = page(client, choices)["messages"]
    assert [message["text"] for message in messages] == ["Vex selected Catfall."]
    assert page(client, choices)["messages"] == []
    assert ModelChoiceReceipt.objects.count() == 1


def test_changed_request_input_and_current_permission_are_rechecked(client, choices):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    assert client.post(url(choices, command=True), values).status_code == 200
    assert (
        client.post(
            url(choices, command=True), {**values, "thing": key(choices.dodge)}
        ).status_code
        == 422
    )
    choices.gang.owner = User.objects.create_user("new-skills-owner")
    choices.gang.save(update_fields=["owner"])
    assert client.post(url(choices, command=True), values).status_code == 404
    assert ModelChoiceReceipt.objects.count() == 1


def test_selection_revalidates_the_placed_offer_and_requires_a_key(client, choices):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    missing = dict(values)
    missing.pop("request_key")
    assert client.post(url(choices, command=True), missing).status_code == 422
    choices.catfall.staged = True
    choices.catfall.save(update_fields=["staged"])
    assert client.post(url(choices, command=True), values).status_code == 422
    assert not ModelChoiceReceipt.objects.exists()
    assert not Assignment.objects.filter(
        miniature_root=choices.model, skill=choices.catfall
    ).exists()
    assert_reconciled(choices.gang)


def test_display_keeps_tiers_power_rating_and_collection_url(client, choices):
    client.force_login(choices.actor)
    response = client.get(url(choices))
    props = response.context["skills_props"]
    assert 'data-react-name="model-skills"' in response.content.decode()
    assert [(group["name"], group["caption"]) for group in props["groups"]] == [
        ("Agility", "Primary"),
        ("Wyrd Powers", "Secondary"),
    ]
    power = props["groups"][1]["options"][0]
    assert power["name"] == "Terrify (Double)"
    # The native offer omits a standalone selection's resulting rating.
    assert power["rating"] == 0
    assert props["action"].endswith(f"?list={choices.collection.pk}")
    assert props["values"]["collection"] == str(choices.collection.pk)
    assert "no-store" in response.headers["Cache-Control"]


def test_expired_session_and_csrf_are_json_refusals(client, choices):
    assert (
        client.post(url(choices, command=True), {"gang": choices.gang.pk}).status_code
        == 401
    )
    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(choices.actor)
    response = guarded.post(
        url(choices, command=True),
        submission(guarded, choices, choices.catfall),
        HTTP_ACCEPT="application/json",
    )
    assert response.status_code == 403
    assert response.headers["Content-Type"].startswith("application/json")
    assert not ModelChoiceReceipt.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_retries_create_one_selection_and_receipt(client, choices):
    from n26.core.skills_workflow import change

    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)

    def submit():
        close_old_connections()
        try:
            data = QueryDict("", mutable=True)
            data.update(values)
            result = change(
                Gang.objects.get(pk=choices.gang.pk),
                User.objects.get(pk=choices.actor.pk),
                choices.model.pk,
                data,
            )
            return result.saved, result.replayed
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(results) == [(True, False), (True, True)]
    assert (
        Assignment.objects.filter(
            miniature_root=choices.model, skill=choices.catfall
        ).count()
        == 1
    )
    assert ModelChoiceReceipt.objects.filter(gang=choices.gang).count() == 1
    assert_reconciled(choices.gang)


def test_more_offered_skills_do_not_add_display_queries(client, choices):
    client.force_login(choices.actor)
    page(client, choices)

    def count():
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url(choices))
            assert response.status_code == 200
        return len(captured)

    before = count()
    for number in range(8):
        create_skill(f"Extra skill {number}", category=choices.agility)
    assert count() <= before


@pytest.mark.parametrize("command", [False, True])
def test_collection_navigation_is_in_the_url_and_the_selected_command(
    client, choices, command
):
    other = create_collection("Alternative skills", contains=[(Skill, choices.agility)])
    primary = section_of(other, "Primary", 0)
    modifier(
        "Alternative placement",
        targets_model(),
        places(choices.agility, primary),
        carried_by=choices.profile,
    )
    client.force_login(choices.actor)
    response = client.get(url(choices), {"list": str(other.pk)})
    props = response.context["skills_props"]
    assert props["values"]["collection"] == str(other.pk)
    assert (
        BeautifulSoup(response.content, "html.parser").title.get_text()
        == f"{other} — Vex | Gyrinx"
    )
    assert props["action"].endswith(f"?list={other.pk}")
    assert (
        next(tab for tab in props["collections"] if tab["current"])["href"]
        == f"?list={other.pk}"
    )
    values = {**props["values"], "thing": key(choices.dodge)}
    assert client.post(url(choices, command=command), values).status_code == (
        200 if command else 302
    )
    receipt = ModelChoiceReceipt.objects.get()
    assert receipt.payload["collection"] == str(other.pk)
    assert_reconciled(choices.gang)


@pytest.mark.parametrize("command", [False, True])
@pytest.mark.parametrize("committed", [False, True])
def test_removed_model_reload_reaches_only_a_read_only_recovery(
    client, choices, command, committed
):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    if committed:
        assert client.post(url(choices, command=command), values).status_code == (
            200 if command else 302
        )
    with operation(choices.gang, actor=choices.actor) as op:
        op.remove(choices.model.membership)
    assert client.get(url(choices)).status_code == 404
    response = client.get(
        url(choices), {"recover": "1", "list": str(choices.collection.pk)}
    )
    assert response.status_code == 200
    props = response.context["skills_props"]
    assert props["recoveryOnly"]
    assert props["groups"] == []
    assert props["switcher"] is None
    assert props["commandHref"] == url(choices, command=True)
    assert props["values"]["collection"] == str(choices.collection.pk)
    response = client.post(url(choices, command=command), values)
    assert response.status_code == ((200 if command else 302) if committed else 409)
    assert_reconciled(choices.gang)


def test_a_removed_selection_command_stays_terminal_after_model_restoration(
    client, choices
):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    with operation(choices.gang, actor=choices.actor) as op:
        op.remove(choices.model.membership)
    response = client.post(url(choices, command=True), values)
    assert response.status_code == 409
    assert response.json()["code"] == "model_removed"
    assert ModelChoiceReceipt.objects.get().result["outcome"] == "removed"
    with operation(choices.gang, actor=choices.actor) as op:
        op.restore(choices.model.membership)
    assert client.post(url(choices, command=True), values).status_code == 409
    assert not Assignment.objects.filter(
        miniature_root=choices.model, skill=choices.catfall
    ).exists()
    assert (
        client.post(
            url(choices, command=True), {**values, "thing": key(choices.dodge)}
        ).status_code
        == 422
    )
    assert ModelChoiceReceipt.objects.count() == 1
    assert_reconciled(choices.gang)


def test_recovery_does_not_expose_removed_model_metadata_to_strangers_or_former_owners(
    client, choices
):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    client.post(url(choices, command=True), values)
    with operation(choices.gang, actor=choices.actor) as op:
        op.remove(choices.model.membership)
    stranger = User.objects.create_user("skills-recovery-stranger")
    outsider = Client()
    outsider.force_login(stranger)
    response = outsider.get(url(choices), {"recover": "1"})
    assert response.status_code == 404
    assert "Vex" not in response.content.decode()
    choices.gang.owner = stranger
    choices.gang.save(update_fields=["owner"])
    client.force_login(choices.actor)
    assert client.get(url(choices), {"recover": "1"}).status_code == 404


def test_consumed_selection_feedback_identifies_a_recovered_save(client, choices):
    client.force_login(choices.actor)
    values = submission(client, choices, choices.catfall)
    client.post(url(choices, command=True), values)
    assert [message["text"] for message in page(client, choices)["messages"]] == [
        "Vex selected Catfall."
    ]
    client.post(url(choices, command=True), values)
    assert [message["text"] for message in page(client, choices)["messages"]] == [
        "Vex selected Catfall. This selection was already saved."
    ]
