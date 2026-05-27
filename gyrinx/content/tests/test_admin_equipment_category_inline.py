import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from gyrinx.content.admin import (
    ContentEquipmentCategoryAdmin,
    ContentFighterEquipmentCategoryLimitInline,
)
from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentFighterEquipmentCategoryLimit,
)

User = get_user_model()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


def test_category_limit_inline_uses_autocomplete_for_fighter():
    """The fighter FK on the limit inline must use an autocomplete widget.

    Rendering it as a full grouped-by-house <select> drew every ContentFighter
    into every inline row (and hit the DB for each fighter's house), making the
    Equipment Category change page extremely slow.
    """
    assert "fighter" in ContentFighterEquipmentCategoryLimitInline.autocomplete_fields


@pytest.mark.django_db
def test_category_change_page_does_not_render_fighter_option_explosion(
    admin_user, content_house, make_content_fighter
):
    """End-to-end: the rendered Equipment Category change page must not dump
    every fighter as an <option> in the limit inline's fighter select.
    """
    category = ContentEquipmentCategory.objects.create(
        name="Crowded Category", group="Gear"
    )
    # Limits are only valid for categories with a fighter restriction.
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
        for i in range(30)
    ]
    # Seed some existing limits so multiple inline rows render.
    for fighter in fighters[:5]:
        ContentFighterEquipmentCategoryLimit.objects.create(
            fighter=fighter, equipment_category=category, limit=1
        )

    request = RequestFactory().get(
        f"/admin/content/contentequipmentcategory/{category.pk}/change/"
    )
    request.user = admin_user

    admin = ContentEquipmentCategoryAdmin(ContentEquipmentCategory, AdminSite())
    response = admin.change_view(request, str(category.pk))
    if hasattr(response, "render"):
        response.render()

    assert response.status_code == 200

    html = response.content.decode()
    # The fighter field renders as an autocomplete widget, not a full dropdown.
    assert "admin-autocomplete" in html
    # Only the selected fighters (one per existing limit) should be present as
    # options — not every fighter in the database.
    assert html.count("Fighter 20") == 0
