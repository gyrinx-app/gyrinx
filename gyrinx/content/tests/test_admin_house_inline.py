import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory

from gyrinx.content.admin import ContentFighterInline, ContentHouseAdmin
from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem

User = get_user_model()


def _make_pack_fighter(house, owner, **kwargs):
    """Create a fighter and attach it to a pack so it becomes pack content.

    Pack content is excluded by the default content manager but surfaced by
    ``all_content()`` — which is what the admin inlines display.
    """
    fighter = ContentFighter.objects.create(house=house, **kwargs)
    pack = CustomContentPack.objects.create(name="Test Pack", owner=owner)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=fighter.id,
    )
    return fighter


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


@pytest.mark.django_db
def test_house_inline_formset_pk_field_includes_pack_content(admin_user):
    """The inline displays pack-content fighters (via ``all_content()``), so the
    formset's hidden pk field must validate against ``all_content()`` too.

    Otherwise the pk field's ``ModelChoiceField`` (built from the default
    manager, which excludes pack content) rejects pack-content rows with a
    "Select a valid choice…" error on the hidden ``id`` field — counted by
    ``AdminErrorList`` (so the "Please correct the errors below" banner shows)
    but never rendered, leaving the house unsaveable. Regression for the silent
    admin error.
    """
    house = ContentHouse.objects.create(name="Packed House")
    normal = ContentFighter.objects.create(
        house=house, type="Normal Leader", category="LEADER", base_cost=100
    )
    pack_fighter = _make_pack_fighter(
        house, admin_user, type="Pack Ganger", category="GANGER", base_cost=50
    )

    request = RequestFactory().get(f"/admin/content/contenthouse/{house.pk}/change/")
    request.user = admin_user
    admin = ContentHouseAdmin(ContentHouse, AdminSite())
    inline = admin.get_inline_instances(request, house)[1]
    assert isinstance(inline, ContentFighterInline)

    fighters = list(inline.get_queryset(request).filter(house=house))
    assert {f.pk for f in fighters} == {normal.pk, pack_fighter.pk}

    FormSet = inline.get_formset(request, house)
    data = {
        "contentfighter_set-TOTAL_FORMS": str(len(fighters)),
        "contentfighter_set-INITIAL_FORMS": str(len(fighters)),
        "contentfighter_set-MIN_NUM_FORMS": "0",
        "contentfighter_set-MAX_NUM_FORMS": "1000",
    }
    for i, f in enumerate(fighters):
        data[f"contentfighter_set-{i}-id"] = str(f.id)
        data[f"contentfighter_set-{i}-house"] = str(house.id)
        data[f"contentfighter_set-{i}-type"] = f.type
        data[f"contentfighter_set-{i}-category"] = f.category
        data[f"contentfighter_set-{i}-base_cost"] = str(f.base_cost)

    formset = FormSet(data=data, instance=house, queryset=inline.get_queryset(request))
    assert formset.is_valid(), formset.errors
    # No form carries a hidden-field error on its pk.
    for form in formset.forms:
        assert "id" not in form.errors


@pytest.mark.django_db
def test_house_change_page_saves_with_pack_content_fighter(admin_user):
    """End-to-end: saving a house whose inline includes a pack-content fighter
    must succeed (redirect), not silently fail with the no-error banner.
    """
    house = ContentHouse.objects.create(name="Packed House E2E")
    normal = ContentFighter.objects.create(
        house=house, type="Normal Leader", category="LEADER", base_cost=100
    )
    pack_fighter = _make_pack_fighter(
        house, admin_user, type="Pack Ganger", category="GANGER", base_cost=50
    )
    fighters = [normal, pack_fighter]

    client = Client()
    client.force_login(admin_user)
    url = f"/admin/content/contenthouse/{house.pk}/change/"

    data = {
        "name": house.name,
        "description": "",
        "gang_skill_tree_count": "0",
        "skill_rank_rules-TOTAL_FORMS": "0",
        "skill_rank_rules-INITIAL_FORMS": "0",
        "skill_rank_rules-MIN_NUM_FORMS": "0",
        "skill_rank_rules-MAX_NUM_FORMS": "1000",
        "contentfighter_set-TOTAL_FORMS": str(len(fighters)),
        "contentfighter_set-INITIAL_FORMS": str(len(fighters)),
        "contentfighter_set-MIN_NUM_FORMS": "0",
        "contentfighter_set-MAX_NUM_FORMS": "1000",
    }
    for i, f in enumerate(fighters):
        data[f"contentfighter_set-{i}-id"] = str(f.id)
        data[f"contentfighter_set-{i}-house"] = str(house.id)
        data[f"contentfighter_set-{i}-type"] = f.type
        data[f"contentfighter_set-{i}-category"] = f.category
        data[f"contentfighter_set-{i}-base_cost"] = str(f.base_cost)

    response = client.post(url, data)
    assert response.status_code == 302, (
        "expected a redirect on successful save; got "
        f"{response.status_code} with errors banner present="
        f"{b'Please correct the errors below' in response.content}"
    )
