"""The storage lifecycle of held N26 ingest sheets."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from n26.library.ingest import store_sheet
from n26.library.models.staging import UploadedSheet

pytestmark = pytest.mark.django_db


def test_direct_deletion_waits_for_commit_and_preserves_shared_legacy_bytes(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    """Delete a shared object only after its final database reference commits."""
    first_owner = User.objects.create_user("first-author")
    second_owner = User.objects.create_user("second-author")
    first = store_sheet(
        first_owner,
        "equipment",
        SimpleUploadedFile("equipment.csv", b"Name,Price\nKnife,5\n"),
    )
    second = UploadedSheet.objects.create(
        owner=second_owner,
        sheet=first.sheet,
        filename=first.filename,
        file=first.file.name,
        lines=first.lines,
    )
    deleted = []
    monkeypatch.setattr(first.file.storage, "delete", deleted.append)

    with django_capture_on_commit_callbacks(execute=True):
        first.delete()

    assert deleted == []

    with django_capture_on_commit_callbacks(execute=True):
        second.delete()
        assert deleted == []

    assert deleted == [first.file.name]
