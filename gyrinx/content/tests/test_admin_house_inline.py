import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from gyrinx.content.admin import ContentFighterInline, ContentHouseAdmin
from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
)

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


def test_house_fighter_inline_omits_expensive_m2m_fields():
    """The ContentHouse change page inlines fighters. Rendering the fighters'
    M2M fields (skills, skill categories, rules) as <select multiple> per row
    made the page take minutes to load. The inline must only expose cheap
    scalar fields; navigation to the full fighter is via the change link.
    """
    inline_fields = set(ContentFighterInline.fields)
    assert inline_fields == {"type", "category", "base_cost"}
    for expensive in (
        "skills",
        "primary_skill_categories",
        "secondary_skill_categories",
        "rules",
    ):
        assert expensive not in inline_fields


@pytest.mark.django_db
def test_house_change_page_does_not_render_m2m_option_explosion(admin_user):
    """End-to-end: the rendered change page for a house with several fighters
    must not contain the per-row skill/rule <option> widgets that caused the
    slowdown.
    """
    house = ContentHouse.objects.create(name="Crowded House")

    # Seed the M2M target tables so the regression would actually explode if
    # the widgets were rendered.
    skill_category = ContentSkillCategory.objects.create(name="Combat")
    skills = [
        ContentSkill.objects.create(name=f"Skill {i}", category=skill_category)
        for i in range(15)
    ]
    rules = [ContentRule.objects.create(name=f"Rule {i}") for i in range(15)]

    for i in range(10):
        fighter = ContentFighter.objects.create(
            type=f"Fighter {i}", category="GANGER", house=house, base_cost=50
        )
        fighter.skills.set(skills)
        fighter.rules.set(rules)

    request = RequestFactory().get(f"/admin/content/contenthouse/{house.pk}/change/")
    request.user = admin_user

    admin = ContentHouseAdmin(ContentHouse, AdminSite())
    response = admin.change_view(request, str(house.pk))
    if hasattr(response, "render"):
        response.render()

    assert response.status_code == 200

    html = response.content.decode()
    # The inline must not render the fighters' M2M widgets per row.
    assert 'name="contentfighter_set-0-skills"' not in html
    assert 'name="contentfighter_set-0-rules"' not in html
    assert 'name="contentfighter_set-0-primary_skill_categories"' not in html
    assert 'name="contentfighter_set-0-secondary_skill_categories"' not in html
    # The cheap scalar field is present, and the inline still lists the fighters.
    assert 'name="contentfighter_set-0-base_cost"' in html
