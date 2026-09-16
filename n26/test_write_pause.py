"""The n26 boundaries onto the platform write pause."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.urls import reverse

from gyrinx.maintenance.registry import operations as maintenance_operations
from gyrinx.site.models import WritePause
from gyrinx.site.write_pause import WritesPaused
from n26.core.campaigns import campaign_operation
from n26.core.deletion import destroy_gang
from n26.core.models import Campaign, Gang
from n26.core.operations import operation
from n26.library.authoring import (
    create_campaign_type,
    create_pack,
    create_trading_post,
    ef_offers_choice,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
    targets_model,
)
from n26.library.ingest import discard_sheets, store_sheet
from n26.library.models import Collection, CollectionSelector, ContentPack, GangType
from n26.library.models.staging import UploadedSheet
from n26.maintenance import task_routes

pytestmark = pytest.mark.django_db(transaction=True)


def pause(reason="Database maintenance is in progress."):
    held = WritePause.objects.get(scope="n26")
    held.state = WritePause.State.PAUSED
    held.reason = reason
    held.generation += 1
    held.save(update_fields=["state", "reason", "generation", "modified"])
    return held


def test_operation_refuses_before_changing_a_gang():
    gang = Gang.objects.create(
        name="Before", gang_type=GangType.objects.create(name="Type")
    )
    pause()

    with pytest.raises(WritesPaused):
        with operation(gang) as op:
            op.rename_gang("After")

    gang.refresh_from_db()
    assert gang.name == "Before"


def test_campaign_operation_refuses_before_writing_an_event():
    owner = User.objects.create_user("arbitrator")
    pack = create_pack("Campaign pack", slug="campaign-pack", owner=owner)
    kind = create_campaign_type("Campaign type", pack=pack)
    campaign = Campaign.objects.create(
        name="Before",
        owner=owner,
        campaign_type=kind,
        pack=pack,
        additions=create_campaign_type("Additions", pack=pack),
    )
    pause()

    with pytest.raises(WritesPaused):
        with campaign_operation(campaign, actor=owner) as op:
            op.rename("After")

    campaign.refresh_from_db()
    assert campaign.name == "Before"
    assert not campaign.events.exists()


def test_public_deletion_refuses_before_removing_a_gang():
    gang = Gang.objects.create(
        name="Still here", gang_type=GangType.objects.create(name="Type")
    )
    pause()

    with pytest.raises(WritesPaused):
        destroy_gang(gang)

    assert Gang.objects.filter(pk=gang.pk).exists()


def test_public_authoring_refuses_before_creating_content():
    pause()

    with pytest.raises(WritesPaused):
        create_pack("Blocked", slug="blocked")

    assert not ContentPack.objects.filter(slug="blocked").exists()


@pytest.mark.parametrize(
    "write",
    [
        create_trading_post,
        targets_model,
        targets_every_model,
        targets_gang,
        targets_gang_alone,
        lambda: ef_offers_choice(object()),
    ],
)
def test_public_authoring_helpers_refuse_while_writes_are_paused(write):
    pause()

    with pytest.raises(WritesPaused):
        write()


def test_trading_post_creation_rolls_back_if_a_selector_fails(monkeypatch):
    def fail_selector(*args, **kwargs):
        raise RuntimeError("selector failed")

    monkeypatch.setattr(CollectionSelector, "of", fail_selector)

    with pytest.raises(RuntimeError, match="selector failed"):
        create_trading_post("Rolled back", contains=[GangType])

    assert not Collection.objects.filter(name="Rolled back").exists()


def test_ingest_upload_refuses_before_storing_a_sheet(user):
    pause()
    upload = SimpleUploadedFile("equipment.csv", b"Name,Price\nKnife,5\n")

    with pytest.raises(WritesPaused):
        store_sheet(user, "equipment", upload)

    assert not UploadedSheet.objects.filter(owner=user).exists()


def test_ingest_replacement_deletes_old_bytes_only_after_commit(user, monkeypatch):
    held = store_sheet(
        user,
        "equipment",
        SimpleUploadedFile("old.csv", b"Name,Price\nKnife,5\n"),
    )
    old_name = held.file.name
    deleted = []
    monkeypatch.setattr(held.file.storage, "delete", deleted.append)

    with transaction.atomic():
        store_sheet(
            user,
            "equipment",
            SimpleUploadedFile("new.csv", b"Name,Price\nSword,10\n"),
        )
        assert deleted == []

    assert deleted == [old_name]


def test_ingest_replacement_rollback_keeps_old_bytes(
    user, monkeypatch, django_capture_on_commit_callbacks
):
    held = store_sheet(
        user,
        "equipment",
        SimpleUploadedFile("old.csv", b"Name,Price\nKnife,5\n"),
    )
    old_name = held.file.name
    deleted = []
    monkeypatch.setattr(held.file.storage, "delete", deleted.append)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError, match="roll back replacement"):
            with transaction.atomic():
                store_sheet(
                    user,
                    "equipment",
                    SimpleUploadedFile("new.csv", b"Name,Price\nSword,10\n"),
                )
                raise RuntimeError("roll back replacement")

    held.refresh_from_db()
    assert callbacks == []
    assert deleted == []
    assert held.file.name == old_name


def test_ingest_discard_rollback_keeps_rows_and_bytes(user, monkeypatch):
    held = store_sheet(
        user,
        "equipment",
        SimpleUploadedFile("old.csv", b"Name,Price\nKnife,5\n"),
    )
    deleted = []
    monkeypatch.setattr(held.file.storage, "delete", deleted.append)

    with pytest.raises(RuntimeError, match="roll back discard"):
        with transaction.atomic():
            assert discard_sheets(user) == 1
            raise RuntimeError("roll back discard")

    assert UploadedSheet.objects.filter(pk=held.pk).exists()
    assert deleted == []


def test_foundations_command_refuses_before_creating_content():
    pause()
    before = ContentPack.objects.count()

    with pytest.raises(WritesPaused):
        call_command("n26_backfill_foundations")

    assert ContentPack.objects.count() == before


def test_unsafe_n26_request_is_refused_before_view_code(client, user):
    gang_type = GangType.objects.create(name="Goliath")
    client.force_login(user)
    pause("A short test pause.")

    response = client.post(
        reverse("n26-create-gang"),
        {
            "name": "Never founded",
            "gang_type": gang_type.pk,
            "starting_credits": "",
            "colour": "",
        },
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert not Gang.objects.filter(name="Never founded").exists()


def test_gang_clone_is_refused_before_creating_its_first_row(client, user):
    gang = Gang.objects.create(
        name="Original", owner=user, gang_type=GangType.objects.create(name="Type")
    )
    client.force_login(user)
    pause()

    response = client.post(
        reverse("n26-clone-gang", args=[gang.pk]), {"name": "Blocked clone"}
    )

    assert response.status_code == 503
    assert list(Gang.objects.values_list("name", flat=True)) == ["Original"]


def test_unsafe_n26_admin_request_is_refused(client):
    administrator = User.objects.create_superuser("administrator")
    client.force_login(administrator)
    pause()

    response = client.post(
        reverse("admin:library_contentpack_add"),
        {"name": "Blocked", "slug": "blocked"},
    )

    assert response.status_code == 503
    assert not ContentPack.objects.filter(slug="blocked").exists()


def test_safe_n26_request_stays_available_with_notice(client, user):
    client.force_login(user)
    pause("A short test pause.")

    response = client.get(reverse("n26-create-gang"))

    assert response.status_code == 200
    assert response.context["write_pause"] is not None
    body = response.content.decode()
    alert = BeautifulSoup(body, "html.parser").find(role="alert")
    assert alert is not None
    assert {"rounded-box", "bg-amber-50", "border-amber-200"} <= set(
        alert.get("class", [])
    )
    assert "Changes paused for maintenance" in body
    assert "A short test pause." in body
    assert "You can still view n26, but you cannot make changes." in body


def test_every_n26_task_route_declares_its_write_scope():
    assert task_routes
    assert {route.write_scope for route in task_routes} == {"n26"}


def test_every_ordinary_n26_maintenance_page_declares_its_write_scope():
    n26_operations = [
        operation
        for operation in maintenance_operations()
        if operation.operation.startswith("n26_")
    ]
    assert n26_operations
    assert {operation.write_scope for operation in n26_operations} == {"n26"}
