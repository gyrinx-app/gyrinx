"""The Options face of a model's own page: the hire listing's option
groups, reopened, with what the model currently takes checked.

``op.rechoose`` has its own suite; these tests are the seam — the page
draws the current pick, and a Save parses through the hire's own
field scheme into the operation.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.text import slugify

from n26.core.models import Gang
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.library.models import DefaultAssignmentSet, OptionGroup

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def gang(tester, gang_type):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=200,
        credits=200,
    )


@pytest.fixture
def ganger(make_profile, make_statline):
    profile = make_profile("Ganger", price=55)
    make_statline(profile)
    return profile


@pytest.fixture
def armament(ganger):
    """A named choose-one group: a knife, or a chainsword for 25 more.
    ``build_hire_entry`` synthesises a default group in front, so the
    named one is group 1 — the same offset the hire rows carry."""
    group = OptionGroup.objects.create(profile=ganger, name="Armament", choose="one")
    plain = DefaultAssignmentSet.objects.create(name="Knife", price=0)
    fancy = DefaultAssignmentSet.objects.create(name="Chainsword", price=25)
    ganger.options.create(
        profile=ganger, group=group, default_set=plain, name="Knife", position=0
    )
    ganger.options.create(
        profile=ganger, group=group, default_set=fancy, name="Chainsword", position=1
    )
    return plain, fancy


@pytest.fixture
def vex(tester, gang, ganger, armament):
    with operation(gang, actor=tester) as op:
        return op.hire(ganger, "Vex")


def options_url(miniature):
    return reverse("n26-fighter-options", args=[miniature.pk])


def field(profile, group):
    return f"{slugify(str(profile.pk))}:{group}"


def props(client, miniature):
    return client.get(options_url(miniature)).context["options_props"]


def submission(client, miniature, selection=None):
    values = dict(props(client, miniature)["values"])
    if selection is not None:
        values["selection"] = json.dumps(selection)
    return values


def option_key(profile, default_set):
    return str(profile.options.get(default_set=default_set).pk)


def command_url(miniature):
    return reverse("n26-fighter-options-command", args=[miniature.pk])


class TestThePage:
    def test_one_react_owner_draws_current_choices_and_card_links(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        response = client.get(options_url(vex))
        page = response.context["options_props"]
        body = response.content.decode()
        assert 'data-react-name="model-options"' in body
        assert 'id="n26-model-card-host"' not in body
        assert page["card"]["name"] == "Vex"
        group = next(group for group in page["groups"] if group["visible"])
        assert [option["checked"] for option in group["options"]] == [True, False]
        assert group["options"][1]["price"] == 25
        assert json.loads(page["values"]["selection"]) == [
            option_key(ganger, armament[0])
        ]
        assert page["values"]["request_key"]
        assert page["values"]["snapshot"]
        assert page["card"]["stored"]["renameHref"].startswith(
            reverse("n26-edit-fighter", args=[vex.pk])
        )
        assert [tab["current"] for tab in page["tabs"]] == [False, False, True]
        assert "no-store" in response.headers["Cache-Control"]

    def test_a_profile_without_choices_keeps_an_empty_page(
        self, client, tester, gang, make_profile
    ):
        plain = make_profile("Juve", price=20)
        with operation(gang, actor=tester) as op:
            fighter = op.hire(plain, "Kid")
        client.force_login(tester)
        page = props(client, fighter)
        assert not any(group["visible"] for group in page["groups"])
        assert (
            options_url(fighter)
            not in client.get(
                reverse("n26-edit-fighter", args=[fighter.pk])
            ).content.decode()
        )

    def test_a_stranger_cannot_read_or_change_the_model(self, client, gang, vex):
        client.force_login(User.objects.create_user("someone-else"))
        assert client.get(options_url(vex)).status_code == 404
        assert client.post(command_url(vex), {"gang": str(gang.pk)}).status_code == 404

    def test_counter_controls_keep_the_native_edit_return_destination(
        self, client, tester, gang, vex
    ):
        from n26.library.authoring import create_counter

        with operation(gang, actor=tester) as op:
            op.assign(create_counter("XP"), miniature=vex)
        client.force_login(tester)
        details = props(client, vex)["card"]["details"]
        counters = [
            part
            for detail in details
            for part in detail["parts"]
            if part["kind"] == "counter"
        ]
        assert counters
        assert all(
            part["control"]["back"] == reverse("n26-edit-fighter", args=[vex.pk])
            for part in counters
        )


class TestSaving:
    @pytest.mark.parametrize("json_command", [False, True])
    def test_changing_options_charges_and_returns_the_difference(
        self, client, tester, gang, ganger, armament, vex, json_command
    ):
        client.force_login(tester)
        target = command_url(vex) if json_command else options_url(vex)
        plain, fancy = armament
        result = client.post(
            target, submission(client, vex, [option_key(ganger, fancy)])
        )
        assert result.status_code == (200 if json_command else 302)
        assert (
            result.json()["nextUrl"] if json_command else result.url
        ) == options_url(vex)
        gang.refresh_from_db()
        vex.refresh_from_db()
        assert gang.credits == 120
        assert vex.rating == 80
        result = client.post(
            target, submission(client, vex, [option_key(ganger, plain)])
        )
        assert result.status_code == (200 if json_command else 302)
        gang.refresh_from_db()
        assert gang.credits == 145
        assert_reconciled(gang)

    def test_native_indexed_fields_keep_the_shared_parser(
        self, client, tester, gang, ganger, vex
    ):
        client.force_login(tester)
        values = submission(client, vex)
        values.pop("selection")
        values[field(ganger, 1)] = "1"
        assert client.post(options_url(vex), values).status_code == 302
        gang.refresh_from_db()
        assert gang.credits == 120
        assert_reconciled(gang)

    def test_an_unaffordable_upgrade_preserves_the_draft_without_a_receipt(
        self, client, tester, gang, ganger, armament, vex
    ):
        from n26.core.models import ModelChoiceReceipt

        gang.starting_credits = 55
        gang.save(update_fields=["starting_credits"])
        with operation(gang, actor=tester) as op:
            op.settle()
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        response = client.post(command_url(vex), values)
        assert response.status_code == 422
        assert response.json()["errors"]["__all__"]
        assert not ModelChoiceReceipt.objects.exists()
        gang.refresh_from_db()
        assert gang.credits == 0
        assert_reconciled(gang)

    def test_stable_choices_survive_catalogue_reordering(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        plain, fancy = armament
        values = submission(client, vex, [option_key(ganger, fancy)])
        ganger.options.filter(default_set=plain).update(position=10)
        ganger.options.filter(default_set=fancy).update(position=0)
        response = client.post(command_url(vex), values)
        assert response.status_code == 200
        gang.refresh_from_db()
        assert gang.credits == 120
        assert_reconciled(gang)

    def test_changed_prices_require_explicit_review(
        self, client, tester, gang, ganger, armament, vex
    ):
        from n26.core.models import ModelChoiceReceipt

        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        armament[1].price = 40
        armament[1].save(update_fields=["price"])
        response = client.post(command_url(vex), values)
        assert response.status_code == 409
        assert response.json()["code"] == "revision_conflict"
        assert response.json()["current"]["options"] == ["Knife"]
        assert not ModelChoiceReceipt.objects.exists()
        gang.refresh_from_db()
        assert gang.credits == 145
        assert_reconciled(gang)

    def test_an_already_desired_selection_is_a_no_op_after_another_tab_saves(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        with operation(gang, actor=tester) as op:
            op.rechoose(vex.membership, option=armament[1])
        assert client.post(command_url(vex), values).status_code == 200
        gang.refresh_from_db()
        assert gang.credits == 120
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "selection", ["not-json", '["not-an-option"]', '["duplicate", "duplicate"]']
    )
    def test_invalid_choices_write_nothing(self, client, tester, gang, vex, selection):
        from n26.core.models import ModelChoiceReceipt

        client.force_login(tester)
        values = submission(client, vex)
        values["selection"] = selection
        assert client.post(command_url(vex), values).status_code == 422
        assert not ModelChoiceReceipt.objects.exists()
        gang.refresh_from_db()
        assert gang.credits == 145
        assert_reconciled(gang)

    def test_missing_command_identity_and_tampered_snapshot_are_refused(
        self, client, tester, gang, vex
    ):
        client.force_login(tester)
        values = submission(client, vex)
        values.pop("request_key")
        assert client.post(command_url(vex), values).status_code == 422
        values = submission(client, vex)
        values["snapshot"] = "tampered"
        assert client.post(command_url(vex), values).status_code == 422
        gang.refresh_from_db()
        assert gang.credits == 145
        assert_reconciled(gang)


class TestReplay:
    def test_replay_confirms_the_original_change_after_a_later_different_edit(
        self, client, tester, gang, ganger, armament, vex
    ):
        from n26.core.models import ModelChoiceReceipt

        client.force_login(tester)
        plain, fancy = armament
        values = submission(client, vex, [option_key(ganger, fancy)])
        assert client.post(command_url(vex), values).status_code == 200
        later = submission(client, vex, [option_key(ganger, plain)])
        assert client.post(command_url(vex), later).status_code == 200
        assert client.post(command_url(vex), values).status_code == 200
        gang.refresh_from_db()
        assert gang.credits == 145
        assert ModelChoiceReceipt.objects.count() == 2
        assert_reconciled(gang)

    def test_replay_survives_a_removed_catalogue_option(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        assert client.post(command_url(vex), values).status_code == 200
        ganger.options.filter(default_set=armament[1]).delete()
        assert client.post(command_url(vex), values).status_code == 200
        gang.refresh_from_db()
        assert gang.credits == 120
        assert_reconciled(gang)

    @pytest.mark.parametrize("native", [False, True])
    def test_replay_after_model_removal_returns_to_the_gang(
        self, client, tester, gang, ganger, armament, vex, native
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        assert client.post(command_url(vex), values).status_code == 200
        with operation(gang, actor=tester) as op:
            op.remove(vex.membership)
        response = client.post(options_url(vex) if native else command_url(vex), values)
        assert response.status_code == (302 if native else 200)
        assert (response.url if native else response.json()["nextUrl"]) == reverse(
            "n26-gang", args=[gang.pk]
        )
        assert_reconciled(gang)

    def test_reusing_a_key_for_changed_input_does_not_write_again(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        assert client.post(command_url(vex), values).status_code == 200
        values["selection"] = json.dumps([option_key(ganger, armament[0])])
        response = client.post(command_url(vex), values)
        assert response.status_code == 422
        gang.refresh_from_db()
        assert gang.credits == 120
        assert_reconciled(gang)

    def test_access_is_rechecked_before_replay(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        assert client.post(command_url(vex), values).status_code == 200
        gang.owner = User.objects.create_user("new-owner")
        gang.save(update_fields=["owner"])
        assert client.post(command_url(vex), values).status_code == 404

    def test_success_feedback_is_queued_once_across_replay(
        self, client, tester, gang, ganger, armament, vex
    ):
        client.force_login(tester)
        values = submission(client, vex, [option_key(ganger, armament[1])])
        client.post(command_url(vex), values)
        client.post(command_url(vex), values)
        page = props(client, vex)
        assert [message["text"] for message in page["messages"]] == [
            "Options saved. 25¢ charged."
        ]
        assert props(client, vex)["messages"] == []


def test_option_count_does_not_add_display_queries(client, tester, gang, ganger, vex):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(tester)
    props(client, vex)

    def count():
        with CaptureQueriesContext(connection) as queries:
            assert client.get(options_url(vex)).status_code == 200
        return len(queries)

    small = count()
    group = ganger.option_groups.first()
    for number in range(8):
        choice = DefaultAssignmentSet.objects.create(
            name=f"Extra {number}", price=number
        )
        ganger.options.create(
            group=group,
            default_set=choice,
            name=f"Extra {number}",
            position=number + 10,
        )
    assert count() <= small


def test_a_stale_tab_cannot_restore_its_old_selection(
    client, tester, gang, ganger, armament, vex
):
    client.force_login(tester)
    old = submission(client, vex, [option_key(ganger, armament[0])])
    with operation(gang, actor=tester) as op:
        op.rechoose(vex.membership, option=armament[1])
    response = client.post(command_url(vex), old)
    assert response.status_code == 409
    gang.refresh_from_db()
    assert gang.credits == 120
    assert_reconciled(gang)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_retries_charge_once(client, tester, gang, ganger, armament, vex):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections
    from django.http import QueryDict

    from n26.core.models import ModelChoiceReceipt
    from n26.core.options_workflow import change

    client.force_login(tester)
    values = submission(client, vex, [option_key(ganger, armament[1])])

    def submit():
        close_old_connections()
        try:
            local_gang = Gang.objects.get(pk=gang.pk)
            actor = User.objects.get(pk=tester.pk)
            data = QueryDict("", mutable=True)
            data.update(values)
            result = change(local_gang, actor, vex.pk, data)
            return result.saved, result.replayed
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(results) == [(True, False), (True, True)]
    assert ModelChoiceReceipt.objects.filter(gang=gang).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 120
    assert_reconciled(gang)


def test_session_expiry_is_a_json_refusal(client, gang, vex):
    response = client.post(command_url(vex), {"gang": str(gang.pk)})
    assert response.status_code == 401
    assert "Sign in" in response.json()["error"]


def test_real_csrf_failure_is_json_and_writes_nothing(tester, gang, vex):
    from django.test import Client

    from n26.core.models import ModelChoiceReceipt

    guarded = Client(enforce_csrf_checks=True)
    guarded.force_login(tester)
    values = submission(guarded, vex)
    response = guarded.post(command_url(vex), values, HTTP_ACCEPT="application/json")
    assert response.status_code == 403
    assert response.headers["Content-Type"].startswith("application/json")
    assert not ModelChoiceReceipt.objects.exists()


def test_a_signed_snapshot_for_another_model_is_refused(
    client, tester, gang, ganger, armament, vex
):
    with operation(gang, actor=tester) as op:
        other = op.hire(ganger, "Other")
    client.force_login(tester)
    values = submission(client, vex, [option_key(ganger, armament[1])])
    assert client.post(command_url(other), values).status_code == 422
    gang.refresh_from_db()
    assert gang.credits == 90
    assert_reconciled(gang)


def test_indexed_native_choices_require_review_after_reordering(
    client, tester, gang, ganger, armament, vex
):
    client.force_login(tester)
    values = submission(client, vex)
    values.pop("selection")
    values[field(ganger, 1)] = "1"
    plain, fancy = armament
    ganger.options.filter(default_set=plain).update(position=10)
    ganger.options.filter(default_set=fancy).update(position=0)
    response = client.post(options_url(vex), values)
    assert response.status_code == 409
    assert response.context["options_props"]["conflict"]
    gang.refresh_from_db()
    assert gang.credits == 145
    assert_reconciled(gang)


@pytest.mark.parametrize("native", [False, True])
def test_a_removed_uncommitted_choice_requires_review(
    client, tester, gang, ganger, armament, vex, native
):
    from n26.core.models import ModelChoiceReceipt

    client.force_login(tester)
    values = submission(client, vex, [option_key(ganger, armament[1])])
    ganger.options.filter(default_set=armament[1]).delete()
    response = client.post(options_url(vex) if native else command_url(vex), values)
    assert response.status_code == 409
    current = (
        response.context["options_props"]["conflict"]
        if native
        else response.json()["current"]
    )
    assert current["options"] == []
    assert not ModelChoiceReceipt.objects.exists()
    gang.refresh_from_db()
    assert gang.credits == 145
    assert_reconciled(gang)


def test_hidden_defaults_do_not_become_explicit_exclusive_choices(
    client, tester, gang, make_profile
):
    profile = make_profile("Shared defaults", price=0)
    shared = DefaultAssignmentSet.objects.create(name="Standard", price=25)
    fancy = DefaultAssignmentSet.objects.create(name="Alternative", price=40)
    profile.options.create(default_set=shared, name="Fixed")
    group = OptionGroup.objects.create(profile=profile, name="Optional", choose="one")
    profile.options.create(group=group, default_set=shared, name="Standard", position=0)
    alternative = profile.options.create(
        group=group, default_set=fancy, name="Alternative", position=1
    )
    with operation(gang, actor=tester) as op:
        miniature = op.hire(profile, "Shared", option=fancy)
    client.force_login(tester)
    values = submission(client, miniature)
    assert json.loads(values["selection"]) == [str(alternative.pk)]
    assert client.post(command_url(miniature), values).status_code == 200
    gang.refresh_from_db()
    assert gang.credits == 135
    assert_reconciled(gang)


def test_rechoose_resolves_shared_defaults_only_once(
    client, tester, gang, make_profile
):
    profile = make_profile("Shared defaults", price=0)
    shared = DefaultAssignmentSet.objects.create(name="Standard", price=25)
    fancy = DefaultAssignmentSet.objects.create(name="Alternative", price=40)
    optional = OptionGroup.objects.create(
        profile=profile, name="Optional", choose="one-or-none", position=0
    )
    mandatory = OptionGroup.objects.create(
        profile=profile, name="Fixed", choose="one", position=1
    )
    profile.options.create(
        group=optional, default_set=shared, name="Optional standard", position=0
    )
    profile.options.create(
        group=optional, default_set=fancy, name="Alternative", position=1
    )
    with operation(gang, actor=tester) as op:
        miniature = op.hire(profile, "Shared", option=fancy)
    profile.options.create(group=mandatory, default_set=shared, name="Fixed standard")
    client.force_login(tester)
    response = client.post(command_url(miniature), submission(client, miniature, []))
    assert response.status_code == 200
    gang.refresh_from_db()
    miniature.refresh_from_db()
    assert gang.credits == 175
    assert miniature.rating == 25
    assert_reconciled(gang)
