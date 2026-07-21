"""Golden-HTML equivalence harness for the cotton big-bang migration.

WORKFLOW
    # 1. On main (or the merge-base), capture goldens:
    git checkout main
    GOLDEN=write pytest gyrinx/core/tests/test_render_equivalence.py -n 0 -q
    # 2. Commit gyrinx/core/tests/goldens/ as the FIRST commit of the branch.
    # 3. On every subsequent commit, this test compares and fails on any diff:
    pytest gyrinx/core/tests/test_render_equivalence.py -n 0 -q

Comparison is BYTE-EXACT by default. Normalisation is opt-in per URL via
ACCEPTED, because every normalisation is a class of change the harness stops
being able to see.
"""

import os
import pathlib
import random

import pytest
from django.urls import reverse

from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.tests.render_world import deterministic_uuids, freeze_timestamps
from gyrinx.core.tests.render_normalise import compare

GOLDEN_DIR = pathlib.Path(__file__).parent / "goldens"
WRITING = os.environ.get("GOLDEN") == "write"


@pytest.fixture
def world(django_user_model, make_content_house, make_content_fighter):
    """A fixed gang the golden pages are rendered from."""
    with deterministic_uuids():
        user = django_user_model.objects.create_user(
            username="goldenuser", password="password"
        )
        house = make_content_house("Golden House")
        cf = make_content_fighter(
            type="Golden Ganger",
            category="GANGER",
            house=house,
            base_cost=50,
        )
        lst = List.objects.create_with_facts(
            name="Golden Gang", content_house=house, owner=user
        )
        for n in ("Alpha", "Beta"):
            ListFighter.objects.create(list=lst, name=n, content_fighter=cf, owner=user)
    freeze_timestamps()
    lst.refresh_from_db()
    return {"user": user, "list": lst, "house": house}


def golden_urls(world):
    """(golden-name, url) pairs. Names are stable filenames."""
    lst = world["list"]
    fighter = lst.fighters().first()
    return [
        ("index", reverse("core:index")),
        ("list-detail", reverse("core:list", args=[lst.id])),
        ("list-about", reverse("core:list-about", args=[lst.id])),
        ("list-edit", reverse("core:list-edit", args=[lst.id])),
        ("list-print", reverse("core:list-print", args=[lst.id])),
        ("lists", reverse("core:lists")),
        ("dice", reverse("core:dice")),
        ("fighter-edit", reverse("core:list-fighter-edit", args=[lst.id, fighter.id])),
    ]


@pytest.mark.django_db
def test_render_equivalence(client, world):
    client.force_login(world["user"])
    GOLDEN_DIR.mkdir(exist_ok=True)
    failures = []

    for name, url in golden_urls(world):
        random.seed(1)  # pins {% cachebuster %} (custom_tags.py:381)
        response = client.get(url)
        assert response.status_code == 200, f"{name} ({url}) -> {response.status_code}"
        actual = response.content.decode()
        path = GOLDEN_DIR / f"{name}.html"

        if WRITING:
            path.write_text(actual)
            continue

        if not path.exists():
            failures.append(f"{name}: no golden at {path} (run with GOLDEN=write)")
            continue

        diff = compare(name, path.read_text(), actual)
        if diff:
            (GOLDEN_DIR / f"{name}.actual.html").write_text(actual)
            failures.append(diff)

    if WRITING:
        pytest.skip(f"wrote {len(golden_urls(world))} goldens to {GOLDEN_DIR}")
    assert not failures, "\n\n".join(failures)
