import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from gyrinx.content.admin import ContentEquipmentCategoryAdmin
from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentFighterEquipmentCategoryLimit,
)
from gyrinx.query import capture_queries

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


def _render_category_change_page(admin_user, category):
    request = RequestFactory().get(
        f"/admin/content/contentequipmentcategory/{category.pk}/change/"
    )
    request.user = admin_user

    admin = ContentEquipmentCategoryAdmin(ContentEquipmentCategory, AdminSite())
    response = admin.change_view(request, str(category.pk))
    if hasattr(response, "render"):
        response.render()
    return response


@pytest.mark.django_db
def test_category_change_page_keeps_grouped_fighter_dropdown(
    admin_user, content_house, make_content_fighter
):
    """The limit inline's fighter field stays a grouped-by-house <select>, so
    the rendered page contains <optgroup> elements for the houses.
    """
    category = ContentEquipmentCategory.objects.create(
        name="Grouped Category", group="Gear"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category, fighter_category="GANGER"
    )
    fighter = make_content_fighter(
        type="Grouped Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    ContentFighterEquipmentCategoryLimit.objects.create(
        fighter=fighter, equipment_category=category, limit=1
    )

    response = _render_category_change_page(admin_user, category)
    assert response.status_code == 200

    html = response.content.decode()
    # Grouping is preserved: the fighter's house renders as an <optgroup>.
    assert f'<optgroup label="{content_house.name}">' in html


@pytest.mark.django_db
def test_category_change_page_does_not_scale_queries_with_fighters(
    admin_user, content_house, make_content_fighter
):
    """Regression: rendering the change page must not issue a query per fighter
    per inline row. Building the grouped choices once (with select_related on
    house) keeps the query count flat regardless of how many fighters exist.
    """
    category = ContentEquipmentCategory.objects.create(
        name="Crowded Category", group="Gear"
    )
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=category, fighter_category="GANGER"
    )

    fighters = [
        make_content_fighter(
            type=f"Fighter {i}",
            category="GANGER",
            house=content_house,
            base_cost=50,
        )
        for i in range(40)
    ]
    # Several existing limits -> several inline rows, each previously rebuilt
    # the full fighter dropdown with an N+1 on house.
    for fighter in fighters[:8]:
        ContentFighterEquipmentCategoryLimit.objects.create(
            fighter=fighter, equipment_category=category, limit=1
        )

    _, info = capture_queries(
        lambda: _render_category_change_page(admin_user, category)
    )

    # With the old per-row group_select this was 8 rows x 40 fighters of house
    # lookups (plus the template form). A flat, generous ceiling catches the
    # regression without being brittle.
    assert info.count < 80, f"too many queries: {info.count}"
