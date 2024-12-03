import json
from pathlib import Path

import pytest

from gyrinx.content.models import ContentSkill


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
