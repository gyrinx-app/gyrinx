import json
from pathlib import Path

import pytest

from gyrinx.content.models import ContentBook, ContentPageRef, ContentSkill


@pytest.mark.django_db
def test_skills_migration():
    root = Path(__file__).parent / "../../../content/exports"
    top_skills_path = root / "top_skills.json"
    with open(top_skills_path, "r") as file:
        top_skills = json.load(file)

    for skill in top_skills[0:100]:
        assert ContentSkill.objects.filter(
            name=skill["skill"]
        ).exists(), f"Skill {skill['skill']} not found"


@pytest.mark.django_db
def test_pageref_books():
    assert len(list(ContentBook.objects.all())) == 8
    assert len(list(ContentBook.objects.filter(obsolete=False))) == 7


@pytest.mark.django_db
def test_pageref_refs():
    assert len(list(ContentPageRef.objects.all())) == 566
    assert ContentPageRef.objects.filter(title="Agility").count() == 1
    agility = ContentPageRef.objects.get(title="Agility")
    assert agility.book.shortname == "Core"
    assert f"{agility}" == "Agility (Skills, Core, p256)"

    charter_master = ContentPageRef.find(
        title="Ironhead Squat Prospectors Charter Master"
    )

    settlement_raid_outcast = ContentPageRef.objects.get(
        title="Settlement Raid",
        book__shortname="Outcast",
    )
    settlement_raid_core = ContentPageRef.objects.get(
        title="Settlement Raid",
        book__shortname="Core",
    )

    assert ContentPageRef.find_similar("Agility") == [agility]
    assert ContentPageRef.find_similar("Charter Master") == [charter_master]
    assert ContentPageRef.find_similar("Settlement Raid") == [
        settlement_raid_outcast,
        settlement_raid_core,
    ]
