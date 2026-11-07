"""Staff-only authoring pages use registered specs and the shipped authoring API.

The tests cover forms, validation, related content, modifiers, documentation and
query growth through real requests and player-facing display structures.
"""

import json
import re
from html import unescape

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User

from n26.library.specs import specs
from n26.library.views import LEAF_KINDS, NESTED_KINDS, RETIRED_KINDS
from n26.tests.fixtures import library_setup

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


@pytest.fixture
@library_setup
def seeded_catalogue(default_pack):
    from n26.library.standard_content import STANDARD_CONTENT

    for item in STANDARD_CONTENT.values():
        item.create()


class TestTheMenuIsBackedBySpecs:
    def test_there_is_something_to_check(self):
        assert {"subtype", "rule", "wargear", "category"} <= set(LEAF_KINDS)

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_kind_has_a_named_editable_spec(self, kind):
        assert LEAF_KINDS[kind] in specs(), (
            f"The authoring menu offers {kind!r} but no spec backs "
            f"{LEAF_KINDS[kind]} — the page could not generate its form."
        )

        spec = specs()[LEAF_KINDS[kind]]
        fieldless = spec.identity is None and not spec.fields
        assert fieldless or spec.identity in spec.fields, (
            f"The {kind} spec says its name field is {spec.identity!r}, but "
            f"its fields are {', '.join(spec.fields)}. Set identity= on the "
            "spec to whichever of those an author reads as the name, or "
            "identity=None only when the configuration has no editable fields."
        )

        from n26.library.specs import Conditions, Union

        spec = specs()[LEAF_KINDS[kind]]
        model = spec.creates
        for name, kind_of_field in spec.fields.items():
            assert not isinstance(kind_of_field, (Union, Conditions)), (
                f"{kind}'s {name} is a {type(kind_of_field).__name__}, which "
                f"has no single column to write back to. Editing would drop "
                f"it — give the kind its own edit path before adding this."
            )
            if getattr(kind_of_field, "written_by", None) is not None:
                # Verb-written fields still need a readable model attribute to
                # initialise edit forms.
                assert hasattr(model, name), (
                    f"{kind}'s {name} is written by a verb but {model.__name__} "
                    f"does not read it back — give the model a {name} property."
                )
                continue
            source = getattr(kind_of_field, "source", None)
            assert source is not None and source[0] is model, (
                f"{kind}'s {name} is not a column on {model.__name__}, so "
                f"editing cannot write it back. Point its source at the "
                f"model the verb makes."
            )

    @pytest.mark.parametrize("kind", ["rule", "weapon", "apply-changes"])
    def test_create_pages_render_plain_switch_and_fieldless_forms(
        self, kind, author, client, default_pack
    ):
        response = client.get(f"/n26/authoring/{kind}/new/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "switchInput" not in body
        switches = form_switches(body)
        if kind == "weapon":
            assert form_switch(body, "is_exclusive")["checked"] is False
        for props in switches:
            assert props["checked"] is True or props["checked"] is False

    def test_every_leaf_listing_renders_with_standard_content(
        self, author, client, seeded_catalogue
    ):
        """Include foundation content without an assignable authoring label when
        exercising every registered listing.
        """
        for kind in sorted(LEAF_KINDS.keys() - NESTED_KINDS):
            response = client.get(f"/n26/authoring/{kind}/")
            assert response.status_code == 200, kind

    def test_an_unknown_kind_is_a_404(self, author, client, default_pack):
        assert client.get("/n26/authoring/gadget/").status_code == 404


class TestFieldlessActionConfigurations:
    """Fieldless configurations still support creation, editing and attachment
    through authoring pages.
    """

    def test_apply_changes_can_be_created_edited_and_attached_to_an_outcome(
        self, author, client, default_pack
    ):
        from n26.library.models import ApplyChanges, Outcome

        created = client.post("/n26/authoring/apply-changes/new/", {})
        operation = ApplyChanges.objects.get()
        assert created.status_code == 302
        detail = f"/n26/authoring/apply-changes/{operation.pk}/"
        assert client.get(detail).status_code == 200
        assert client.post(detail, {"act": "edit"}).status_code == 302

        attached = client.post(
            "/n26/authoring/outcome/new/",
            {"name": "Clear counters", "apply_changes": str(operation.pk)},
        )
        assert attached.status_code == 302
        assert Outcome.objects.get(name="Clear counters").apply_changes == operation

    def test_recruitment_rule_has_a_form_and_builder_creates_one_for_an_action(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_slot_type
        from n26.library.models import Action, RecruitmentAllowanceRule

        created = client.post("/n26/authoring/recruitment-allowance-rule/new/", {})
        rule = RecruitmentAllowanceRule.objects.get()
        assert created.status_code == 302
        detail = f"/n26/authoring/recruitment-allowance-rule/{rule.pk}/"
        assert client.get(detail).status_code == 200
        assert client.post(detail, {"act": "edit"}).status_code == 302

        tier = create_slot_type("Rig augmentation")
        created_action = client.post(
            "/n26/authoring/action/new/",
            {
                "draft": json.dumps(
                    {
                        "name": "Recruitment augmentation",
                        "timing": "recruitment",
                        "useMode": "recruitment",
                        "outcomes": [
                            {
                                "name": "Choose rig tier",
                                "operation": "augment",
                                "slotType": str(tier.pk),
                            }
                        ],
                    }
                )
            },
        )
        assert created_action.status_code == 302
        action = Action.objects.get(name="Recruitment augmentation")
        assert action.recruitment_allowance_rule is not None
        assert action.recruitment_allowance_rule != rule
        outcome = action.outcomes.get().outcome
        assert outcome.name == "Choose rig tier"
        assert outcome.augment_carried_item.slot_type == tier


class TestRankThresholdWords:
    """Rank-table details name the configured counter without adding a query per
    threshold.
    """

    def test_the_detail_names_its_counter_with_fixed_query_growth(
        self, author, client, default_pack
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library import authoring

        kills = authoring.create_counter("Kill Count")
        table = authoring.create_rank_table("Hunt ranks", kills, thresholds=[4])
        url = f"/n26/authoring/rank-table/{table.pk}/"
        client.get(url)
        with CaptureQueriesContext(connection) as one:
            first = client.get(url)
        assert "Kill Count" in first.content.decode()

        for threshold in range(5, 15):
            authoring.add_rank_threshold(table, threshold)
        with CaptureQueriesContext(connection) as many:
            client.get(url)
        assert len(many) == len(one)


class TestAffiliationIsRetiredFromTheMenu:
    """Retired kinds have no creation links; existing affiliation content remains
    readable.
    """

    def test_the_index_offers_none_of_the_retired_kinds(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/").content.decode()

        for kind in RETIRED_KINDS:
            assert f"/n26/authoring/{kind}/new/" not in body, kind

    def test_a_retired_kinds_page_still_opens(self, author, client, default_pack):
        from n26.tests.sandbox.actions import create_affiliation

        held = create_affiliation("Clanless")

        listing = client.get("/n26/authoring/affiliation/")
        page = client.get(f"/n26/authoring/affiliation/{held.pk}/")

        assert listing.status_code == 200
        assert page.status_code == 200
        assert "Clanless" in page.content.decode()
        assert "/n26/authoring/affiliation/new/" not in listing.content.decode()
        listing_body = listing.content.decode()
        assert re.search(
            r'<a href="/n26/authoring/affiliation/"[^>]*aria-current="page"',
            listing_body,
        )
        assert ">Affiliations</span>" in listing_body


class TestTheIndex:
    def test_lists_every_kind_with_its_count(self, author, client, default_pack):
        from n26.library.authoring import create_subtype

        create_subtype("Leader")
        response = client.get("/n26/authoring/")
        assert response.status_code == 200
        body = response.content.decode()
        assert "subtype" in body
        assert "wargear" in body


class TestTheListingIsForReading:
    """Kind listings show model documentation and links to separate create and edit
    pages.
    """

    def test_it_documents_the_kind_and_offers_a_way_in(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/rule/").content.decode()

        # Assert model documentation using text unaffected by HTML escaping.
        assert "A named special rule on a fighter" in body
        assert "/n26/authoring/rule/new/" in body

    def test_it_carries_no_create_form(self, author, client, default_pack):
        body = client.get("/n26/authoring/subtype/").content.decode()
        assert 'name="qualifier"' not in body

    def test_every_row_links_to_its_own_page(self, author, client, default_pack):
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        body = client.get("/n26/authoring/subtype/").content.decode()

        assert f"/n26/authoring/subtype/{mounted.pk}/" in body

    def test_a_row_carries_what_the_search_matches_on(
        self, author, client, default_pack
    ):
        """Client-side search requires lowercased searchable text alongside the
        displayed name.
        """
        from n26.library.authoring import create_rule

        create_rule("Lead Ritual", annotation="Leader only")
        body = client.get("/n26/authoring/rule/").content.decode()

        assert "lead ritual" in body
        assert "Lead Ritual" in body


class TestCreatingALeaf:
    def test_the_form_shows_the_models_own_words(self, author, client, default_pack):
        from n26.library.models import Rule

        body = client.get("/n26/authoring/rule/new/").content.decode()
        assert str(Rule._meta.get_field("annotation").help_text) in body

    def test_a_valid_submit_performs_the_verb(self, author, client, default_pack):
        from n26.library.models import Subtype

        response = client.post("/n26/authoring/subtype/new/", {"name": "Mounted"})
        assert response.status_code == 302

        row = Subtype.objects.get(name="Mounted")
        assert row.pack == default_pack

        body = client.get("/n26/authoring/subtype/").content.decode()
        assert "Mounted" in body

    def test_a_priced_wargear_with_a_home(self, author, client, default_pack):
        from n26.library.authoring import create_category
        from n26.library.models import Wargear

        home = create_category("Personal Equipment", "Field Armour")
        response = client.post(
            "/n26/authoring/wargear/new/",
            {
                "name": "Seven-pointed breastplate",
                "price": "20",
                "trade_point_price": "1",
                "category": str(home.pk),
            },
        )
        assert response.status_code == 302
        armour = Wargear.objects.get(name="Seven-pointed breastplate")
        assert armour.price == 20
        assert armour.category == home

    def test_a_rule_keeps_its_annotation(self, author, client, default_pack):
        from n26.library.models import Rule

        client.post(
            "/n26/authoring/rule/new/",
            {"name": "Lead Ritual", "annotation": "Leader only"},
        )
        assert str(Rule.objects.get(name="Lead Ritual")) == "Lead Ritual (Leader only)"

    def test_a_duplicate_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.models import Subtype

        client.post("/n26/authoring/subtype/new/", {"name": "Mounted"})
        response = client.post("/n26/authoring/subtype/new/", {"name": "Mounted"})

        assert response.status_code == 200
        assert "already exists in this pack" in response.content.decode()
        assert Subtype.objects.filter(name="Mounted").count() == 1

    def test_a_duplicate_stat_refuses_in_words_too(self, author, client, default_pack):
        """Duplicate-stat errors must identify Movement even though Stat uses
        full_name rather than name.
        """
        from n26.library.models import Stat

        made = {"short_name": "M", "full_name": "Movement"}
        client.post("/n26/authoring/stat/new/", made)
        response = client.post("/n26/authoring/stat/new/", made)

        assert response.status_code == 200
        body = response.content.decode()
        assert "already exists in this pack" in body
        assert "Movement" in body
        assert Stat.objects.filter(full_name="Movement").count() == 1

    def test_a_missing_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.models import Counter

        response = client.post("/n26/authoring/counter/new/", {"name": ""})
        assert response.status_code == 200
        assert "required" in response.content.decode()
        assert Counter.objects.count() == 0


class TestEditingOne:
    """Detail pages edit existing content through prefixed, spec-generated forms."""

    def test_the_page_opens_the_form_on_what_is_there(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_rule

        rule = create_rule("Lead Ritual", annotation="Leader only")
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()

        assert 'value="Lead Ritual"' in body
        assert 'value="Leader only"' in body

    def test_a_change_is_saved(self, author, client, default_pack):
        from n26.library.authoring import create_rule
        from n26.library.models import Rule

        rule = create_rule("Lead Ritual", annotation="Leader only")
        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "edit",
                "edit-name": "Lead Rite",
                "edit-annotation": "Leaders only",
            },
        )

        assert response.status_code == 302
        rule.refresh_from_db()
        assert rule.name == "Lead Rite"
        assert rule.annotation == "Leaders only"
        assert Rule.objects.count() == 1

    def test_a_field_cleared_is_cleared(self, author, client, default_pack):
        """Submit empty optional fields so clearing a value reaches the saved
        content.
        """
        from n26.library.authoring import create_rule

        rule = create_rule("Lead Ritual", annotation="Leader only")
        client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {"act": "edit", "edit-name": "Lead Ritual", "edit-annotation": ""},
        )

        rule.refresh_from_db()
        assert rule.annotation == ""

    def test_a_stored_nought_is_drawn_as_nought(self, author, client, default_pack):
        """Zero is a valid price and must not disappear when the form renders falsy
        values.
        """
        from n26.library.authoring import create_weapon

        saw = create_weapon("Heavy rock saw", price=0, slots=2, is_exclusive=True)

        body = client.get(f"/n26/authoring/weapon/{saw.pk}/").content.decode()

        assert re.search(r'name="edit-price"[^>]*value="0"', body)

    def test_a_row_priced_at_nought_saves(self, author, client, default_pack):
        from n26.library.authoring import create_weapon

        saw = create_weapon("Heavy rock saw", price=0, slots=2, is_exclusive=True)

        response = client.post(
            f"/n26/authoring/weapon/{saw.pk}/",
            {
                "act": "edit",
                "edit-name": "Heavy rock saw",
                "edit-slots": "2",
                "edit-price": "0",
                "edit-trade_point_price": "",
                "edit-is_exclusive": "on",
            },
        )

        assert response.status_code == 302
        saw.refresh_from_db()
        assert saw.price == 0

    def test_an_empty_number_box_leaves_the_number_alone(
        self, author, client, default_pack
    ):
        """Empty numeric controls preserve existing values in nonnullable fields."""
        from n26.library.authoring import create_weapon

        lasgun = create_weapon("Lasgun", price=15, slots=1)

        response = client.post(
            f"/n26/authoring/weapon/{lasgun.pk}/",
            {"act": "edit", "edit-name": "Lasgun", "edit-price": "", "edit-slots": ""},
        )

        assert response.status_code == 302
        lasgun.refresh_from_db()
        assert (lasgun.price, lasgun.slots) == (15, 1)

    def test_the_author_help_box_carries_its_name(self, author, client, default_pack):
        """The help control needs a submitted name so unrelated edits do not clear
        its stored value.
        """
        from n26.library.authoring import create_weapon

        lasgun = create_weapon(
            "Lasgun", price=15, library_author_help="Standard issue everywhere."
        )

        body = client.get(f"/n26/authoring/weapon/{lasgun.pk}/").content.decode()

        assert 'name="edit-library_author_help"' in body
        assert "Standard issue everywhere." in body

    def test_a_duplicate_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_subtype

        create_subtype("Mounted")
        wyrd = create_subtype("Wyrd")
        response = client.post(
            f"/n26/authoring/subtype/{wyrd.pk}/",
            {"act": "edit", "edit-name": "Mounted"},
        )

        assert response.status_code == 200
        assert "already exists in this pack" in response.content.decode()
        wyrd.refresh_from_db()
        assert wyrd.name == "Wyrd"

    def test_editing_leaves_the_parts_alone(self, author, client, default_pack):
        from n26.library.authoring import add_weapon_profile, create_weapon

        weapon = create_weapon("Lasgun", price=15)
        add_weapon_profile(weapon)
        client.post(
            f"/n26/authoring/weapon/{weapon.pk}/",
            {
                "act": "edit",
                "edit-name": "Lasgun",
                "edit-price": "20",
                "edit-slots": "1",
            },
        )

        weapon.refresh_from_db()
        assert weapon.price == 20
        assert weapon.profiles.count() == 1

    def test_the_two_forms_on_a_page_do_not_share_a_control(
        self, author, client, default_pack
    ):
        """Prefix the edit form so controls from different forms cannot share IDs or
        affect each other.
        """
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Lasgun", price=15)
        body = client.get(f"/n26/authoring/weapon/{weapon.pk}/").content.decode()

        assert body.count('id="id_is_exclusive"') <= 1, (
            "Two controls share an id, so the browser cannot tell them "
            "apart — give one of the forms a prefix."
        )
        assert 'name="edit-is_exclusive"' in body

    def test_a_toggle_left_alone_stays_off(self, author, client, default_pack):
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Lasgun", price=15)
        client.post(
            f"/n26/authoring/weapon/{weapon.pk}/",
            {
                "act": "edit",
                "edit-name": "Lasgun",
                "edit-price": "20",
                "edit-slots": "1",
            },
        )

        weapon.refresh_from_db()
        assert weapon.price == 20
        assert weapon.is_exclusive is False

    def test_a_switch_opens_on_the_value_it_has(self, author, client, default_pack):
        """React switch props must carry the stored value, including true values."""
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Handbow", price=15, is_exclusive=True)
        body = client.get(f"/n26/authoring/weapon/{weapon.pk}/").content.decode()

        assert form_switch(body, "edit-is_exclusive")["checked"] is True

    def test_an_exclusive_weapon_stays_exclusive(self, author, client, default_pack):
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Handbow", price=15, is_exclusive=True)
        client.post(
            f"/n26/authoring/weapon/{weapon.pk}/",
            {
                "act": "edit",
                "edit-name": "Handbow",
                "edit-price": "20",
                "edit-slots": "1",
                "edit-is_exclusive": "on",
            },
        )

        weapon.refresh_from_db()
        assert weapon.is_exclusive is True


class TestSwitchingBetweenKindsAndRows:
    """Authoring navigation links kinds and sibling content, marks the current page
    and provides consistent shortcuts.
    """

    def test_the_bar_offers_the_other_kinds_from_a_page_that_is_not_one(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/foundations/").content.decode()
        assert 'aria-label="Switch kind"' in body
        assert "/n26/authoring/weapon/" in body

    def test_a_kinds_page_marks_itself(self, author, client, default_pack):
        body = client.get("/n26/authoring/category/").content.decode()
        assert re.search(
            r'<a href="/n26/authoring/category/"[^>]*aria-current="page"', body
        )
        assert not re.search(
            r'<a href="/n26/authoring/weapon/"[^>]*aria-current="page"', body
        )

    def test_the_listing_offers_the_kinds_beside_its_heading(
        self, author, client, default_pack
    ):
        """Give the two kind switchers distinct accessible names."""
        body = client.get("/n26/authoring/category/").content.decode()
        assert 'aria-label="Switch kind"' in body
        assert 'aria-label="Switch to another kind of content"' in body

    def test_a_rows_page_offers_the_other_rows(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        other = create_rule("Sump Sense")
        body = client.get(f"/n26/authoring/rule/{here.pk}/").content.decode()

        # Use the model label rather than the URL slug in the accessible name.
        assert 'aria-label="Switch to another special rule"' in body
        assert f"/n26/authoring/rule/{other.pk}/" in body
        assert "Sump Sense" in body

    def test_the_row_being_looked_at_is_marked(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        other = create_rule("Sump Sense")
        body = client.get(f"/n26/authoring/rule/{here.pk}/").content.decode()

        assert re.search(
            rf'<a href="/n26/authoring/rule/{here.pk}/"[^>]*aria-current="page"', body
        )
        assert not re.search(
            rf'<a href="/n26/authoring/rule/{other.pk}/"[^>]*aria-current="page"', body
        )

    def test_the_bars_switcher_is_linked_to_where_the_page_sits(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")

        listing = client.get("/n26/authoring/rule/").content.decode()
        assert ">Special rules</span>" in listing
        rows_page = client.get(f"/n26/authoring/rule/{here.pk}/").content.decode()
        assert ">Special rules</span>" in rows_page

        elsewhere = client.get("/n26/authoring/foundations/").content.decode()
        assert ">Content library</span>" in elsewhere
        assert 'href="/n26/authoring/"' in elsewhere

    def test_the_collection_page_sits_under_its_own_kind(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_collection

        row = create_collection("Armoury")
        body = client.get(f"/n26/authoring/collection/{row.pk}/").content.decode()
        assert ">Collections</span>" in body
        assert 'href="/n26/authoring/collection/"' in body

    def test_every_authoring_page_answers_the_two_chords(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        for url in ("/n26/authoring/rule/", f"/n26/authoring/rule/{here.pk}/"):
            body = client.get(url).content.decode()
            assert 'aria-keyshortcuts="Alt+Shift+F"' in body, url
            assert 'aria-keyshortcuts="Alt+Shift+R"' in body, url

    def test_the_sibling_list_does_not_grow_with_the_kind(
        self, author, client, default_pack
    ):
        """Adding sibling content must not increase queries for a detail page."""
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        client.get(
            f"/n26/authoring/rule/{here.pk}/"
        )  # Warm lazy setup before measuring query growth.

        def queries():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext

            with CaptureQueriesContext(connection) as captured:
                client.get(f"/n26/authoring/rule/{here.pk}/")
            return len(captured)

        before = queries()
        for index in range(30):
            create_rule(f"Rule {index:02d}")
        assert queries() == before


class TestTheDoorIsStaffed:
    def test_anonymous_is_sent_to_log_in(self, client, default_pack):
        response = client.get("/n26/authoring/subtype/")
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_a_plain_user_is_not_staff(self, client, default_pack):
        client.force_login(User.objects.create_user("player"))
        response = client.get("/n26/authoring/subtype/")
        assert response.status_code == 302
        assert "login" in response["Location"]


class TestSections:
    """Categories select a stored section and configure whether their items use a
    separate card heading.
    """

    def test_the_category_form_picks_a_section(self, author, client, default_pack):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["create_category"])()
        from django import forms as django_forms

        assert isinstance(form.fields["section"], django_forms.ModelChoiceField)
        assert form.fields["section"].required

    def test_a_section_then_a_category_under_it(self, author, client, default_pack):
        from n26.library.models import Category, Section

        client.post(
            "/n26/authoring/section/new/", {"name": "Ranged Weapons", "position": "0"}
        )
        heading = Section.objects.get(name="Ranged Weapons")

        client.post(
            "/n26/authoring/category/new/",
            {"name": "Auto/Stub Weapons", "section": str(heading.pk), "position": "1"},
        )
        made = Category.objects.get(name="Auto/Stub Weapons")
        assert made.section == heading
        assert str(made) == "Ranged Weapons: Auto/Stub Weapons"

    def test_a_category_can_be_told_to_draw_its_own_row(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_category
        from n26.library.models import Category

        home = create_category("Wargear", "Gene-smithing")
        assert not home.draws_its_own_row

        page = f"/n26/authoring/category/{home.pk}/"
        body = client.get(page).content.decode()
        assert 'name="edit-draws_its_own_row"' in body
        assert form_switch(body, "edit-draws_its_own_row")["checked"] is False

        edit = {
            "act": "edit",
            "edit-section": str(home.section.pk),
            "edit-name": "Gene-smithing",
            "edit-position": "0",
        }
        client.post(page, {**edit, "edit-draws_its_own_row": "on"})
        home.refresh_from_db()
        assert home.draws_its_own_row

        body = client.get(page).content.decode()
        assert form_switch(body, "edit-draws_its_own_row")["checked"] is True

        # An omitted checkbox on an edit means false.
        client.post(page, edit)
        home.refresh_from_db()
        assert not home.draws_its_own_row

        client.post(
            "/n26/authoring/category/new/",
            {
                "name": "Chem-alchemy Elixirs",
                "section": str(home.section.pk),
                "position": "1",
                "draws_its_own_row": "on",
            },
        )
        assert Category.objects.get(name="Chem-alchemy Elixirs").draws_its_own_row

    def test_named_headings_are_founded_once(self, default_pack):
        """Creating categories by section name must reuse the existing section."""
        from n26.library.authoring import create_category
        from n26.library.models import Section

        create_category("Skills", "Combat")
        create_category("Skills", "Savant")
        assert Section.objects.filter(name="Skills").count() == 1


class TestAProfilesHome:
    """Profiles may select a category whose label includes its section."""

    def test_the_create_form_offers_a_home(
        self, author, client, default_pack, fighter_type, gang_type
    ):
        from n26.library.authoring import create_category

        create_category("Escher", "Champions")
        body = client.get("/n26/authoring/profile/new/").content.decode()

        assert "Escher: Champions" in body

    def test_a_created_profile_keeps_its_home(
        self, author, client, default_pack, fighter_type, gang_type
    ):
        from n26.library.authoring import create_category
        from n26.library.models import Profile

        champions = create_category("Escher", "Champions")
        response = client.post(
            "/n26/authoring/profile/new/",
            {
                "name": "Death-maiden",
                "profile_type": str(fighter_type.pk),
                "gang_type": str(gang_type.pk),
                "price": "115",
                "category": str(champions.pk),
            },
        )

        assert response.status_code == 302
        assert Profile.objects.get(name="Death-maiden").category == champions

    def test_a_home_is_optional(
        self, author, client, default_pack, fighter_type, gang_type
    ):
        from n26.library.models import Profile

        response = client.post(
            "/n26/authoring/profile/new/",
            {
                "name": "Wyld Runner",
                "profile_type": str(fighter_type.pk),
                "gang_type": str(gang_type.pk),
                "price": "60",
                "category": "",
            },
        )

        assert response.status_code == 302
        assert Profile.objects.get(name="Wyld Runner").category is None

    def test_the_edit_page_opens_on_the_home_it_has(
        self, author, client, default_pack, fighter_type, gang_type
    ):
        from n26.library.authoring import create_category, create_profile

        champions = create_category("Escher", "Champions")
        profile = create_profile(
            "Death-maiden", fighter_type, gang_type, price=115, category=champions
        )

        body = client.get(f"/n26/authoring/profile/{profile.pk}/").content.decode()
        picker = re.search(
            r'<select\s+name="edit-category".*?</select>', body, re.S
        ).group()
        chosen = re.search(r"<option[^>]*\bselected\b[^>]*>", picker).group()
        assert str(champions.pk) in chosen

    def test_the_home_can_be_changed(
        self, author, client, default_pack, fighter_type, gang_type
    ):
        from n26.library.authoring import create_category, create_profile

        champions = create_category("Escher", "Champions")
        gangers = create_category("Escher", "Gangers")
        profile = create_profile(
            "Death-maiden", fighter_type, gang_type, price=115, category=champions
        )

        response = client.post(
            f"/n26/authoring/profile/{profile.pk}/",
            {
                "act": "edit",
                "edit-name": "Death-maiden",
                "edit-profile_type": str(fighter_type.pk),
                "edit-gang_type": str(gang_type.pk),
                "edit-price": "115",
                "edit-category": str(gangers.pk),
            },
        )

        assert response.status_code == 302
        profile.refresh_from_db()
        assert profile.category == gangers


class TestAuthorHelp:
    """Assignable forms store optional help for content authors."""

    def test_every_assignable_leaf_form_offers_help(self):
        """Discover assignable kinds from the menu so new kinds must expose author
        help too.
        """
        from n26.library.models.assignable import Assignable

        checked = 0
        for kind, verb_name in LEAF_KINDS.items():
            spec = specs()[verb_name]
            model = spec.creates
            if issubclass(model, Assignable):
                assert "library_author_help" in spec.fields, (
                    f"The {kind} form has no help field — authors cannot "
                    f"say what the thing is for."
                )
                checked += 1
        assert checked >= 8

    def test_the_field_speaks_to_content_authors(self):
        from n26.library.models import Wargear

        words = str(Wargear._meta.get_field("library_author_help").help_text)
        assert "For content authors" in words

    def test_help_is_stored_from_the_form(self, author, client, default_pack):
        from n26.library.models import Subtype

        client.post(
            "/n26/authoring/subtype/new/",
            {
                "name": "Wyrd",
                "library_author_help": (
                    "The psyker mark — powers machinery keys off this."
                ),
            },
        )
        row = Subtype.objects.get(name="Wyrd")
        assert row.library_author_help == (
            "The psyker mark — powers machinery keys off this."
        )

    def test_help_stays_optional(self, author, client, default_pack):
        from n26.library.models import Subtype

        client.post("/n26/authoring/subtype/new/", {"name": "Mounted"})
        assert Subtype.objects.get(name="Mounted").library_author_help == ""


class TestFamilies:
    """Model families determine the authoring menu groups."""

    def test_every_assignable_declares_a_family(self):
        from django.apps import apps

        from n26.library.models.assignable import Assignable, Family

        checked = 0
        for model in apps.get_app_config("library").get_models():
            if issubclass(model, Assignable):
                assert isinstance(getattr(model, "family", None), Family), (
                    f"{model.__name__} is an Assignable with no family — "
                    f"the authoring menu cannot place it."
                )
                checked += 1
        assert checked >= 15

    def test_every_menu_kind_has_a_family(self):
        from n26.library.models.assignable import Family
        from n26.library.views import _model_for

        for kind, verb_name in LEAF_KINDS.items():
            model = _model_for(specs()[verb_name])
            assert isinstance(getattr(model, "family", None), Family), kind

    def test_the_index_groups_by_family(self, author, client, default_pack):
        # Restrict ordering checks to the table; navigation repeats these kind labels.
        body = client.get("/n26/authoring/").content.decode()
        body = body[body.index('scope="colgroup"') :]
        positions = [
            # Compare the escaped label as rendered.
            re.search(
                rf'scope="colgroup".*?>\s*{re.escape(label.replace("&", "&amp;"))}\s*<',
                body,
                re.S,
            ).start()
            for label in ("Base", "Model", "Gear", "Gang", "Slots & Pickables")
        ]
        assert positions == sorted(positions)
        assert positions[2] < body.index("wargear")
        assert positions[3] < body.index("gang-type")

    def test_the_family_table(self):
        """Pin each model's family so regrouping requires an explicit change."""
        from n26.library.models import (
            Affiliation,
            Category,
            Collection,
            Counter,
            GangType,
            Hidden,
            Pickable,
            Picklist,
            Profile,
            Rule,
            Section,
            Skill,
            Slot,
            SlotType,
            Subtype,
            Trait,
            Wargear,
            Weapon,
            WeaponProfile,
        )
        from n26.library.models.assignable import Family

        by_family = {
            Family.BASE: [Rule, Counter, Hidden, Section, Category],
            Family.MODEL: [Subtype, Skill],
            Family.GEAR: [Trait, Wargear, Weapon, WeaponProfile],
            Family.GANG: [
                GangType,
                Profile,
                Affiliation,
                Collection,
            ],
            Family.CHOICE: [SlotType, Pickable, Picklist, Slot],
        }
        for family, models in by_family.items():
            for model in models:
                assert model.family == family, model.__name__


class TestHelpRendersOnTheForm:
    def test_the_textarea_and_the_guardrail_are_on_the_page(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/subtype/new/").content.decode()
        assert "<textarea" in body
        assert "For content authors" in body


class TestTheCarriers:
    """Hidden content is created without modifiers; affiliation creation is
    unavailable.
    """

    def test_a_hidden_carrier(self, author, client, default_pack):
        from n26.library.models import Hidden

        client.post(
            "/n26/authoring/hidden/new/",
            {
                "name": "Deploys the Trazior",
                "library_author_help": "Rides the option set that spawns the gun.",
            },
        )
        made = Hidden.objects.get(name="Deploys the Trazior")
        assert made.library_author_help.startswith("Rides the option set")
        assert not made.modifiers.exists()

    def test_the_chosen_carrier_is_no_longer_offered(
        self, author, client, default_pack
    ):
        response = client.get("/n26/authoring/affiliation/new/")
        posted = client.post("/n26/authoring/affiliation/new/", {"name": "Clan House"})

        assert response.status_code == 404
        assert posted.status_code == 404


@pytest.fixture
def legacy(default_pack):
    """A slot type with one pickable, one picklist and one slot."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
    )

    slot_type = create_slot_type(
        "Gang Legacy", plural_name="Gang Legacies", allows_repeats=False
    )
    cawdor = create_pickable("Cawdor", slot_type)
    houses = create_picklist("House Legacies", slot_type, members=[cawdor])
    create_slot("House legacy", slot_type, houses, label="Gang Legacy")
    return slot_type


@pytest.fixture
def affiliation(default_pack):
    """An unrelated slot type for detecting choices that escape the current type."""
    from n26.library.authoring import (
        create_pickable,
        create_picklist,
        create_slot_type,
    )

    slot_type = create_slot_type("Affiliation")
    clanless = create_pickable("Clanless", slot_type)
    create_picklist("Affiliations", slot_type, members=[clanless])
    return slot_type


class TestAuthoringSlotDismissal:
    def test_new_slots_allow_dismissal_by_default(self, author, client, default_pack):
        from bs4 import BeautifulSoup

        response = client.get("/n26/authoring/slot/new/")
        checkbox = BeautifulSoup(response.content, "html.parser").find(
            "input", attrs={"name": "allow_dismissal"}
        )
        assert checkbox.has_attr("checked")
        assert "Allow dismissal" in response.content.decode()

    @pytest.mark.parametrize("allowed", [True, False])
    def test_an_author_can_create_and_change_the_setting(
        self, author, client, legacy, allowed
    ):
        from n26.library.models import Slot

        original = Slot.objects.get()
        data = {
            "name": "Another choice",
            "slot_type": str(legacy.pk),
            "picklist": str(original.picklist_id),
            "min_picks": "1",
            "max_picks": "1",
            "assigned_to": "bearer",
            "position": "0",
        }
        if allowed:
            data["allow_dismissal"] = "on"
        response = client.post("/n26/authoring/slot/new/", data)
        assert response.status_code == 302
        slot = Slot.objects.get(name="Another choice")
        assert slot.allow_dismissal is allowed

        data.pop("slot_type")
        data.pop("allow_dismissal", None)
        if not allowed:
            data["allow_dismissal"] = "on"
        edit = {f"edit-{name}": value for name, value in data.items()}
        response = client.post(
            f"/n26/authoring/slot/{slot.pk}/", {"act": "edit", **edit}
        )
        assert response.status_code == 302
        slot.refresh_from_db()
        assert slot.allow_dismissal is not allowed


class TestASlotTypeIsSettledWhenAThingIsMade:
    """A pickable, picklist or slot cannot change slot type after creation.

    Changing it would invalidate relationships between existing choices and their
    options.
    """

    KINDS = ("pickable", "picklist", "slot")

    def page(self, client, kind, row):
        return client.get(f"/n26/authoring/{kind}/{row.pk}/").content.decode()

    def test_no_page_that_corrects_one_offers_it(self, author, client, legacy):
        from n26.library.models import Pickable, Picklist, Slot

        for kind, model in zip(self.KINDS, (Pickable, Picklist, Slot), strict=True):
            body = self.page(client, kind, model.objects.get())
            assert 'name="edit-name"' in body, kind
            assert 'name="edit-slot_type"' not in body, kind

    def test_the_page_that_makes_one_still_asks(self, author, client, default_pack):
        for kind in self.KINDS:
            body = client.get(f"/n26/authoring/{kind}/new/").content.decode()
            assert 'name="slot_type"' in body, kind

    def test_pickable_help_explains_the_fields_without_lecturing_authors(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/pickable/new/").content.decode()

        assert "An option for a choice, such as an augmentation tier" in body
        assert "Groups this option with the slots that can offer it." in body
        assert "Shown under this option on the choice page." in body
        assert "Distinguishes same-named options in the library." in body
        assert "Players cannot add staged content to gangs" in body
        assert "Write your own summary" not in body
        assert "copy rules text" not in body

        slot_body = client.get("/n26/authoring/slot/new/").content.decode()
        assert "Shown above the options on the choice page." in slot_body
        assert "copy rules text" not in slot_body

    def test_a_slot_type_posted_by_hand_does_not_land(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Slot

        slot = Slot.objects.get()
        response = client.post(
            f"/n26/authoring/slot/{slot.pk}/",
            {
                "act": "edit",
                "edit-name": slot.name,
                "edit-slot_type": str(affiliation.pk),
                "edit-picklist": str(slot.picklist_id),
                "edit-label": slot.label,
                "edit-min_picks": "1",
                "edit-max_picks": "1",
                "edit-assigned_to": slot.assigned_to,
                "edit-position": "0",
            },
        )

        assert response.status_code == 302
        slot.refresh_from_db()
        assert slot.slot_type == legacy

    def test_the_rest_of_the_choice_still_saves(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Slot

        slot = Slot.objects.get()
        client.post(
            f"/n26/authoring/slot/{slot.pk}/",
            {
                "act": "edit",
                "edit-name": slot.name,
                "edit-picklist": str(slot.picklist_id),
                "edit-label": "Ancestry",
                "edit-introduction": "Pick a legacy for this fighter.",
                "edit-min_picks": "0",
                "edit-max_picks": "2",
                "edit-assigned_to": slot.assigned_to,
                "edit-position": "0",
            },
        )

        slot.refresh_from_db()
        assert (slot.label, slot.min_picks, slot.max_picks) == ("Ancestry", 0, 2)
        assert slot.introduction == "Pick a legacy for this fighter."

    def test_an_author_can_revise_a_pickables_player_summary(
        self, author, client, legacy
    ):
        from n26.library.models import Pickable

        pick = Pickable.objects.get(name="Cawdor")
        response = client.post(
            f"/n26/authoring/pickable/{pick.pk}/",
            {
                "act": "edit",
                "edit-name": pick.name,
                "edit-summary": "A short explanation for this choice.",
                "edit-rating_contribution": "0",
            },
        )

        assert response.status_code == 302
        pick.refresh_from_db()
        assert pick.summary == "A short explanation for this choice."


class TestASlotTypeReadsAsAKind:
    """A slot-type detail page links its own pickables, picklists and slots."""

    def page(self, client, slot_type):
        return client.get(f"/n26/authoring/slot-type/{slot_type.pk}/").content.decode()

    def test_the_menu_has_no_page_for_a_deleted_kind(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/").content.decode()

        for kind in ("archetype", "skill-tree", "specialisation"):
            assert f"/n26/authoring/{kind}/" not in body, kind

    def test_the_index_groups_the_choice_kinds_together(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/").content.decode()
        heading = re.search(
            r'scope="colgroup".*?>\s*Slots &amp; Pickables\s*<', body, re.S
        )
        assert heading, "the index has no Slots & Pickables group"
        rest = body[heading.start() :].lower()
        for kind in ("slot type", "pickable", "picklist", "slot"):
            assert kind in rest, kind

    def test_it_lists_the_slot_types_own_parts(self, author, client, legacy):
        body = self.page(client, legacy)

        assert "Cawdor" in body
        assert "House Legacies" in body
        assert "House legacy" in body

    def test_every_part_leads_to_its_own_page(self, author, client, legacy):
        from n26.library.models import Pickable, Picklist, Slot

        body = self.page(client, legacy)

        for kind, model in (
            ("pickable", Pickable),
            ("picklist", Picklist),
            ("slot", Slot),
        ):
            row = model.objects.get()
            assert f'href="/n26/authoring/{kind}/{row.pk}/"' in body, kind

    def test_another_slot_types_parts_stay_off_it(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Pickable, Picklist

        body = self.page(client, legacy)

        # Use IDs because navigation also contains the unrelated kind label.
        assert str(Pickable.objects.get(name="Clanless").pk) not in body
        assert str(Picklist.objects.get(name="Affiliations").pk) not in body

    def test_the_bar_sits_under_slot_types(self, author, client, legacy):
        body = self.page(client, legacy)

        assert ">Slot types</span>" in body
        assert 'href="/n26/authoring/slot-type/"' in body

    def test_it_answers_the_two_chords(self, author, client, legacy):
        body = self.page(client, legacy)

        assert 'aria-keyshortcuts="Alt+Shift+F"' in body
        assert 'aria-keyshortcuts="Alt+Shift+R"' in body

    def test_a_stranger_is_sent_to_log_in(self, client, legacy):
        response = client.get(f"/n26/authoring/slot-type/{legacy.pk}/")

        assert response.status_code == 302
        assert "login" in response["Location"]


class TestBuildingASlotTypeFromItsOwnPage:
    """Parts created on a slot-type page inherit that type and offer only compatible
    relationships.
    """

    def test_a_pickable_is_made_in_this_slot_type(self, author, client, legacy):
        from n26.library.models import Pickable

        response = client.post(
            f"/n26/authoring/slot-type/{legacy.pk}/",
            {
                "act": "pickable",
                "name": "Escher",
                "qualifier": "",
                "summary": "A short explanation written by the author.",
            },
        )

        assert response.status_code == 302
        made = Pickable.objects.get(name="Escher")
        assert made.slot_type == legacy
        assert made.summary == "A short explanation written by the author."

    def test_a_list_is_made_in_this_slot_type(self, author, client, legacy):
        from n26.library.models import Picklist

        client.post(
            f"/n26/authoring/slot-type/{legacy.pk}/",
            {"act": "picklist", "name": "Ogryn Legacy"},
        )

        assert Picklist.objects.get(name="Ogryn Legacy").slot_type == legacy

    def test_a_choice_is_made_in_this_slot_type(self, author, client, legacy):
        from n26.library.models import Picklist, Slot

        houses = Picklist.objects.get(name="House Legacies")

        client.post(
            f"/n26/authoring/slot-type/{legacy.pk}/",
            {
                "act": "slot",
                "name": "Second legacy",
                "picklist": str(houses.pk),
                "label": "Gang Legacy",
                "introduction": "Pick this fighter's legacy.",
                "min_picks": "1",
                "max_picks": "1",
                "assigned_to": "bearer",
                "position": "0",
            },
        )

        made = Slot.objects.get(name="Second legacy")
        assert (made.slot_type, made.picklist) == (legacy, houses)
        assert made.introduction == "Pick this fighter's legacy."

    def test_the_choice_form_offers_this_slot_types_lists_and_no_others(
        self, author, client, legacy, affiliation
    ):
        """A slot can offer only picklists belonging to its slot type."""
        from n26.library.models import Picklist

        body = client.get(f"/n26/authoring/slot-type/{legacy.pk}/").content.decode()
        elsewhere = Picklist.objects.get(name="Affiliations")

        assert f'value="{Picklist.objects.get(name="House Legacies").pk}"' in body
        assert f'value="{elsewhere.pk}"' not in body

    def test_a_duplicate_name_refuses_in_words(self, author, client, legacy):
        response = client.post(
            f"/n26/authoring/slot-type/{legacy.pk}/",
            {"act": "pickable", "name": "Cawdor"},
        )

        assert response.status_code == 200
        assert "already exists in this pack" in response.content.decode()

    def test_the_slot_type_itself_is_edited_here(self, author, client, legacy):
        client.post(
            f"/n26/authoring/slot-type/{legacy.pk}/",
            {"act": "edit", "edit-name": "Gang Legacy", "edit-plural_name": "Legacies"},
        )
        legacy.refresh_from_db()

        assert legacy.plural == "Legacies"
        assert not legacy.allows_repeats


class TestMakingAChoiceFromScratch:
    """Standalone slot creation validates that the selected picklist belongs to the
    selected slot type.
    """

    def post(self, client, **fields):
        return client.post(
            "/n26/authoring/slot/new/",
            {
                "name": "Muddled",
                "min_picks": "1",
                "max_picks": "1",
                "assigned_to": "bearer",
                "position": "0",
                **fields,
            },
        )

    def test_a_choice_over_its_own_slot_types_list_is_made(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Picklist, Slot

        houses = Picklist.objects.get(name="House Legacies")

        response = self.post(client, slot_type=str(legacy.pk), picklist=str(houses.pk))

        assert response.status_code == 302
        assert Slot.objects.get(name="Muddled").picklist == houses

    def test_a_choice_over_another_slot_types_list_is_refused_in_words(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Picklist, Slot

        elsewhere = Picklist.objects.get(name="Affiliations")

        response = self.post(
            client, slot_type=str(legacy.pk), picklist=str(elsewhere.pk)
        )

        assert response.status_code == 200
        assert (
            "Affiliations lists Affiliation pickables, and this is a Gang "
            "Legacy choice." in response.content.decode()
        )
        assert not Slot.objects.filter(name="Muddled").exists()

    def test_correcting_one_offers_only_its_own_slot_types_lists(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Picklist, Slot

        choice = Slot.objects.get()
        body = client.get(f"/n26/authoring/slot/{choice.pk}/").content.decode()

        assert f'value="{Picklist.objects.get(name="House Legacies").pk}"' in body
        assert str(Picklist.objects.get(name="Affiliations").pk) not in body


class TestTheAboutColumnPointsAtTheChoicePages:
    """Choice descriptions link related picklists and slots to their authoring pages."""

    def test_a_pickables_page_leads_to_its_list_and_the_slot_offering_it(
        self, author, client, legacy
    ):
        from n26.library.models import Pickable, Picklist, Slot

        cawdor = Pickable.objects.get(name="Cawdor")
        body = client.get(f"/n26/authoring/pickable/{cawdor.pk}/").content.decode()

        assert "Listed in House Legacies." in body
        assert f'href="/n26/authoring/picklist/{Picklist.objects.get().pk}/"' in body
        assert f'href="/n26/authoring/slot/{Slot.objects.get().pk}/"' in body

    def test_a_choices_page_says_what_it_asks_for(self, author, client, legacy):
        from n26.library.models import Slot

        choice = Slot.objects.get()
        body = client.get(f"/n26/authoring/slot/{choice.pk}/").content.decode()

        assert "Asks for one Gang Legacy, chosen from House Legacies." in body


class TestAPicklistsOwnPage:
    """Picklist details manage membership and explain the slot type, dependent slots
    and roll-table configuration.
    """

    def picklist(self):
        from n26.library.models import Picklist

        return Picklist.objects.get(name="House Legacies")

    def test_it_lists_what_it_offers(self, author, client, legacy):
        body = client.get(
            f"/n26/authoring/picklist/{self.picklist().pk}/"
        ).content.decode()

        assert "Cawdor" in body
        assert "Add a pickable" in body

    def test_every_pickable_it_lists_leads_to_its_own_page(
        self, author, client, legacy
    ):
        from n26.library.models import Pickable

        body = client.get(
            f"/n26/authoring/picklist/{self.picklist().pk}/"
        ).content.decode()
        cawdor = Pickable.objects.get(name="Cawdor")

        assert f'href="/n26/authoring/pickable/{cawdor.pk}/"' in body

    def test_it_names_the_slot_type_it_belongs_to(self, author, client, legacy):
        """Show the slot type in navigation because it is absent from the immutable
        edit fields.
        """
        body = client.get(
            f"/n26/authoring/picklist/{self.picklist().pk}/"
        ).content.decode()

        assert f'href="/n26/authoring/slot-type/{legacy.pk}/"' in body
        assert "Gang Legacy" in body

    def test_a_pickable_and_a_slot_name_their_slot_type_too(
        self, author, client, legacy
    ):
        """Show immutable slot-type membership in navigation for pickables and slots
        too.
        """
        from n26.library.models import Pickable, Slot

        for kind, pk in (
            ("pickable", Pickable.objects.get(name="Cawdor").pk),
            ("slot", Slot.objects.get().pk),
        ):
            body = client.get(f"/n26/authoring/{kind}/{pk}/").content.decode()
            assert f'href="/n26/authoring/slot-type/{legacy.pk}/"' in body, kind

    def test_it_lists_the_slots_drawing_on_it(self, author, client, legacy):
        from n26.library.models import Slot

        body = client.get(
            f"/n26/authoring/picklist/{self.picklist().pk}/"
        ).content.decode()
        drawn_on_by = Slot.objects.get(name="House legacy")

        assert "Slots drawing on this picklist" in body
        assert f'href="/n26/authoring/slot/{drawn_on_by.pk}/"' in body
        assert "House legacy" in body

    def test_a_list_no_slot_draws_on_says_so(self, author, client, legacy):
        from n26.library.authoring import create_picklist

        unasked = create_picklist("Ogryn Legacy", legacy)
        body = client.get(f"/n26/authoring/picklist/{unasked.pk}/").content.decode()

        assert "No slot draws on this picklist yet" in body

    def test_a_pickable_is_added_through_the_page(self, author, client, legacy):
        from n26.library.authoring import create_pickable

        escher = create_pickable("Escher", legacy)
        houses = self.picklist()

        client.post(
            f"/n26/authoring/picklist/{houses.pk}/",
            {"pickable": str(escher.pk), "label_override": "", "position": "1"},
        )

        assert [member.label for member in houses.members.all()] == ["Cawdor", "Escher"]

    def test_a_roll_tables_results_are_worked_on_the_table_page(
        self, author, client, legacy
    ):
        """Edit roll-table results on the dedicated page that also checks band
        coverage; ordinary picklists retain their member form.
        """
        from n26.library.authoring import create_picklist

        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        body = client.get(f"/n26/authoring/picklist/{table.pk}/").content.decode()
        assert "Roll table" in body
        assert "0 of 36 rolls covered" in body
        assert 'name="pickable"' not in body
        assert f'href="/n26/authoring/picklists/{table.pk}/table/"' in body

        plain = create_picklist("Plain", legacy)
        body = client.get(f"/n26/authoring/picklist/{plain.pk}/").content.decode()
        assert 'name="pickable"' in body
        assert 'name="roll_low"' in body and 'name="roll_high"' in body

    def test_a_roll_tables_page_leads_each_row_with_its_band(
        self, author, client, legacy
    ):
        from n26.library.authoring import (
            add_picklist_member,
            create_pickable,
            create_picklist,
        )

        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        add_picklist_member(
            table, create_pickable("Out Cold", legacy), roll_low=21, roll_high=26
        )
        page = client.get(f"/n26/authoring/picklist/{table.pk}/").content.decode()
        assert "21-26" in page

        listing = client.get("/n26/authoring/picklist/").content.decode()
        assert "rolled on a D66" in listing

    def test_the_create_form_offers_the_dice(self, author, client, legacy):
        body = client.get("/n26/authoring/picklist/new/").content.decode()
        assert 'name="dice"' in body and 'name="roll_selects"' in body
        assert 'value="d66"' in body

    def test_the_form_offers_no_dice_at_all(self, author, client, legacy):
        """Render a blank option so the browser does not select dice or a roll mode
        for an ordinary picklist.
        """
        body = client.get("/n26/authoring/picklist/new/").content.decode()
        for field in ("dice", "roll_selects"):
            select = body[body.index(f'name="{field}"') :]
            select = select[: select.index("</select>")]
            assert 'value=""' in select, field

    def test_a_list_made_with_no_dice_is_an_ordinary_list(self, author, client, legacy):
        from n26.library.models import Picklist

        client.post(
            "/n26/authoring/picklist/new/",
            {
                "name": "Plain",
                "slot_type": str(legacy.pk),
                "dice": "",
                "roll_selects": "",
            },
        )
        made = Picklist.objects.get(name="Plain")
        assert made.dice == "" and made.roll_selects == ""

    def test_a_half_roll_table_is_refused_on_the_form(self, author, client, legacy):
        from n26.library.models import Picklist

        body = client.post(
            "/n26/authoring/picklist/new/",
            {
                "name": "Half",
                "slot_type": str(legacy.pk),
                "dice": "d66",
                "roll_selects": "",
            },
        ).content.decode()
        assert "names its dice and how" in body
        assert not Picklist.objects.filter(name="Half").exists()

    def test_editing_a_table_into_half_a_one_is_refused_on_the_form(
        self, author, client, legacy
    ):
        """Report incomplete roll-table configuration before a database constraint
        can be misreported as a duplicate name.
        """
        from n26.library.authoring import create_picklist
        from n26.library.models import Picklist

        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        body = client.post(
            f"/n26/authoring/picklist/{table.pk}/",
            {
                "act": "edit",
                "edit-name": "Injuries",
                "edit-dice": "d66",
                "edit-roll_selects": "",
            },
        ).content.decode()

        assert "names its dice and how" in body
        assert "already exists" not in body
        assert Picklist.objects.get(pk=table.pk).roll_selects == "band"

    def test_an_ordinary_edit_still_saves(self, author, client, legacy):
        from n26.library.authoring import create_picklist
        from n26.library.models import Picklist

        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        response = client.post(
            f"/n26/authoring/picklist/{table.pk}/",
            {
                "act": "edit",
                "edit-name": "Lasting Injuries",
                "edit-dice": "d66",
                "edit-roll_selects": "band",
            },
        )

        assert response.status_code == 302
        assert Picklist.objects.get(pk=table.pk).name == "Lasting Injuries"

    def test_a_roll_table_links_to_its_table_page(self, author, client, legacy):
        from n26.library.authoring import create_picklist

        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        body = client.get(f"/n26/authoring/picklist/{table.pk}/").content.decode()
        assert f'href="/n26/authoring/picklists/{table.pk}/table/"' in body

        plain = create_picklist("Plain", legacy)
        body = client.get(f"/n26/authoring/picklist/{plain.pk}/").content.decode()
        assert "/table/" not in body

    def test_a_band_on_a_list_with_no_dice_is_refused_on_the_page(
        self, author, client, legacy
    ):
        from n26.library.authoring import create_pickable
        from n26.library.models import PicklistMember

        escher = create_pickable("Escher", legacy)
        body = client.post(
            f"/n26/authoring/picklist/{self.picklist().pk}/",
            {
                "pickable": str(escher.pk),
                "label_override": "",
                "position": "1",
                "roll_low": "11",
                "roll_high": "11",
            },
        ).content.decode()
        assert "names no dice" in body
        assert not PicklistMember.objects.filter(pickable=escher).exists()

    def test_only_this_slot_types_pickables_are_offered(
        self, author, client, legacy, affiliation
    ):
        from n26.library.models import Pickable

        body = client.get(
            f"/n26/authoring/picklist/{self.picklist().pk}/"
        ).content.decode()
        elsewhere = Pickable.objects.get(name="Clanless")

        assert f'value="{Pickable.objects.get(name="Cawdor").pk}"' in body
        assert f'value="{elsewhere.pk}"' not in body

    def test_a_pickable_is_taken_off_at_its_own_address(self, author, client, legacy):
        from n26.library.models import Pickable, PicklistMember

        member = PicklistMember.objects.get()
        asked = client.get(
            f"/n26/authoring/picklist-members/{member.pk}/remove/"
        ).content.decode()

        assert "Stop offering Cawdor?" in asked

        client.post(f"/n26/authoring/picklist-members/{member.pk}/remove/")

        assert not PicklistMember.objects.exists()
        assert Pickable.objects.filter(name="Cawdor").exists()


class TestARollTablesOwnPage:
    """Roll-table pages show ordered bands, gaps, overlaps and unreachable results."""

    @pytest.fixture
    def table(self, legacy):
        from n26.library.authoring import (
            add_picklist_member,
            create_pickable,
            create_picklist,
        )

        from_bands = [
            ("Out Cold", 21, 26),
            ("Lesson Learnt", 11, 11),
            ("Grievous Wound", 31, 46),
        ]
        table = create_picklist("Injuries", legacy, dice="d66", roll_selects="band")
        for name, low, high in from_bands:
            add_picklist_member(
                table, create_pickable(name, legacy), roll_low=low, roll_high=high
            )
        return table

    def url(self, table):
        from django.urls import reverse

        return reverse("authoring-picklist-table", args=[table.pk])

    def test_the_address_resolves_ahead_of_the_kind_catch_all(
        self, author, client, table
    ):
        assert self.url(table) == f"/n26/authoring/picklists/{table.pk}/table/"
        assert client.get(self.url(table)).status_code == 200

    def test_the_rows_come_in_roll_order_with_their_bands(self, author, client, table):
        body = client.get(self.url(table)).content.decode()
        assert body.index("Lesson Learnt") < body.index("Out Cold")
        assert body.index("Out Cold") < body.index("Grievous Wound")
        assert "21-26" in body

    def test_it_says_what_is_unclaimed(self, author, client, table):
        body = client.get(self.url(table)).content.decode()
        assert "19 of 36 rolls covered" in body
        assert "12" in body and "61" in body

    def test_it_says_when_a_roll_is_claimed_twice(self, author, client, table, legacy):
        from n26.library.authoring import add_picklist_member, create_pickable

        add_picklist_member(
            table, create_pickable("Also Out Cold", legacy), roll_low=26
        )
        body = client.get(self.url(table)).content.decode()
        assert "claimed by more than one result" in body
        assert "Also Out Cold" in body

    def test_a_whole_table_says_so(self, author, client, legacy):
        from n26.library.authoring import (
            add_picklist_member,
            create_pickable,
            create_picklist,
        )

        whole = create_picklist("Whole", legacy, dice="d6", roll_selects="band")
        add_picklist_member(
            whole, create_pickable("All of it", legacy), roll_low=1, roll_high=6
        )
        body = client.get(self.url(whole)).content.decode()
        assert "6 of 6 rolls covered" in body

    def test_a_bandless_result_keeps_a_covered_table_out_of_the_clear(
        self, author, client, legacy
    ):
        """Full roll coverage does not make a bandless result reachable."""
        from n26.library.authoring import (
            add_picklist_member,
            create_pickable,
            create_picklist,
        )

        table = create_picklist("Whole", legacy, dice="d6", roll_selects="band")
        add_picklist_member(
            table, create_pickable("All of it", legacy), roll_low=1, roll_high=6
        )
        add_picklist_member(table, create_pickable("Unrollable", legacy))
        body = client.get(self.url(table)).content.decode()
        assert "Unrollable has no band, so no roll lands on it" in body

    def test_a_row_is_added_from_the_page_with_its_band(
        self, author, client, table, legacy
    ):
        from n26.library.authoring import create_pickable
        from n26.library.models import PicklistMember

        eye = create_pickable("Eye Injury", legacy)
        client.post(
            self.url(table),
            {
                "pickable": str(eye.pk),
                "label_override": "",
                "position": "9",
                "roll_low": "51",
                "roll_high": "51",
            },
        )
        assert PicklistMember.objects.get(pickable=eye).band == "51"

    def test_the_picker_offers_only_this_slot_types_pickables(
        self, author, client, table, affiliation
    ):
        from n26.library.models import Pickable

        elsewhere = Pickable.objects.get(name="Clanless")
        body = client.get(self.url(table)).content.decode()
        assert f'value="{elsewhere.pk}"' not in body
        assert f'value="{Pickable.objects.get(name="Cawdor").pk}"' in body

    def test_an_ordinary_lists_table_address_leads_back_to_its_page(
        self, author, client, legacy
    ):
        from n26.library.authoring import create_picklist

        plain = create_picklist("Plain", legacy)
        response = client.get(self.url(plain))
        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/picklist/{plain.pk}/"

    def test_the_page_is_the_staff_s(self, client, db, legacy, table):
        from django.contrib.auth.models import User

        client.force_login(User.objects.create_user("player"))
        response = client.get(self.url(table))
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_the_page_reads_flat_as_the_table_grows(
        self, author, client, legacy, table
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_picklist_member, create_pickable

        def grow(indices):
            for index in indices:
                add_picklist_member(
                    table, create_pickable(f"Result {index}", legacy), roll_low=51
                )

        grow(range(2))
        with CaptureQueriesContext(connection) as few:
            assert client.get(self.url(table)).status_code == 200
        grow(range(2, 12))
        with CaptureQueriesContext(connection) as more:
            assert client.get(self.url(table)).status_code == 200
        assert len(more) <= len(few)


class TestKindHelp:
    """Authoring pages derive kind definitions and menu summaries from model
    docstrings.
    """

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_kind_has_a_definition_and_a_menu_summary(self, kind):
        from n26.library.views import _model_for, kind_help

        paragraphs = kind_help(_model_for(specs()[LEAF_KINDS[kind]]))
        assert paragraphs, f"{kind} has no docstring — the page cannot say what it is"
        assert len(paragraphs[0]) > 20

        from n26.library.views import _model_for, kind_summary

        summary = kind_summary(_model_for(specs()[LEAF_KINDS[kind]]))
        assert summary.endswith("."), f"{kind}: not a sentence"
        assert len(summary) < 120, f"{kind}: too long for a menu row"

    def test_the_emphasis_in_a_docstring_is_drawn_and_not_typed(self):
        """Render docstring emphasis as HTML rather than showing Markdown
        punctuation.
        """
        from n26.library.models import Slot
        from n26.library.views import kind_help

        said = " ".join(kind_help(Slot))

        assert "<strong>Hidden</strong>" in said
        assert "**" not in said

    def test_the_menu_shows_the_definitions(self, author, client, default_pack):
        body = client.get("/n26/authoring/").content.decode()
        assert "A carrier for effects that draws no row of its own." in body

    def test_the_page_leads_with_the_definition(self, author, client, default_pack):
        body = client.get("/n26/authoring/hidden/").content.decode()
        assert "A carrier for effects that draws no row of its own." in body

    def test_literals_become_code_and_html_cannot_leak(self):
        from n26.library.views import kind_help

        class Pretend:
            """Uses ``code`` and a <tag> that must not render."""

        (paragraph,) = kind_help(Pretend)
        assert "<code>code</code>" in paragraph
        assert "&lt;tag&gt;" in paragraph


@pytest.fixture
def weapon_statline_type(make_stat):
    """Weapon characteristics SR, LR, Str, AP and L, reusing shared stat definitions."""
    from n26.library.models import Stat, StatlineType, StatlineTypeStat

    statline_type = StatlineType.objects.create(name="Weapon")
    definitions = [
        ("SR", "Short Range", {"is_inches": True}),
        ("LR", "Long Range", {"is_inches": True}),
        ("Str", "Strength", {}),
        ("AP", "Armour Piercing", {}),
        ("L", "Lethality", {}),
    ]
    for position, (short, full, flags) in enumerate(definitions):
        # Reuse stat definitions across statline types, including fighter and weapon
        # Strength.
        stat = Stat.objects.filter(full_name=full).first() or make_stat(
            short, full, **flags
        )
        StatlineTypeStat.objects.create(
            statline_type=statline_type, stat=stat, position=position
        )
    return statline_type


class TestWeapons:
    """Weapons and their profiles are authored through pages, then rendered on model
    cards.
    """

    def make_autogun(self, client, weapon_statline_type):
        response = client.post(
            "/n26/authoring/weapon/new/",
            {
                "name": "Autogun",
                "slots": "1",
                "statline_type": str(weapon_statline_type.pk),
                "price": "20",
                "trade_point_price": "0",
            },
        )
        from n26.library.models import Weapon

        return response, Weapon.objects.get(name="Autogun")

    def add_line(self, client, weapon, **payload):
        """Submit a weapon profile through its creation page."""
        return client.post(
            f"/n26/authoring/weapons/{weapon.pk}/add-profile/",
            {"trade_point_price": "0", **payload},
        )

    def test_creating_a_weapon_lands_on_its_page(
        self, author, client, default_pack, weapon_statline_type
    ):
        response, autogun = self.make_autogun(client, weapon_statline_type)
        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/weapon/{autogun.pk}/"
        assert autogun.price == 20
        assert autogun.statline_type == weapon_statline_type

        body = client.get(response["Location"]).content.decode()
        assert "None yet" in body

    def test_the_statline_form_is_shaped_by_the_weapon(
        self, author, client, default_pack, weapon_statline_type
    ):
        _, autogun = self.make_autogun(client, weapon_statline_type)
        body = client.get(
            f"/n26/authoring/weapons/{autogun.pk}/add-profile/"
        ).content.decode()
        # Characteristic fields follow this weapon's statline type rather than fixed
        # spec fields.
        for short, field in (
            ("SR", "short_range"),
            ("LR", "long_range"),
            ("Str", "strength"),
            ("AP", "armour_piercing"),
            ("L", "lethality"),
        ):
            assert f'name="{field}"' in body
            assert re.search(rf">\s*{re.escape(short)}\s*</th>", body)
        assert 'placeholder="4&quot;"' in body

    def test_a_renamed_column_is_renamed_wherever_the_page_prints_it(
        self, author, client, default_pack, make_stat
    ):
        """Use the statline type's label override in both the editor and the weapon-
        profile summary.
        """
        from n26.library.authoring import (
            add_stat_to_statline_type,
            create_statline_type,
        )

        strength = make_stat("S", "Strength")
        shape = create_statline_type("Weapon")
        add_stat_to_statline_type(shape, strength, short_name_override="Str")

        _, autogun = self.make_autogun(client, shape)
        self.add_line(client, autogun, name="Standard", price="0", strength="3")

        editor = client.get(
            f"/n26/authoring/weapons/{autogun.pk}/add-profile/"
        ).content.decode()
        assert re.search(r">\s*Str\s*</th>", editor)
        assert not re.search(r">\s*S\s*</th>", editor)

        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        assert "Str 3" in body
        assert "S 3" not in body

    def test_adding_the_mandatory_profile_with_its_stats_and_traits(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        _, autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")

        response = self.add_line(
            client,
            autogun,
            name="Standard",
            price="0",
            traits=[str(rapid_fire.pk)],
            short_range="8",
            long_range="24",
            strength="3",
            armour_piercing="-",
            lethality="1",
        )
        assert response.status_code == 302

        profile = WeaponProfile.objects.get(weapon=autogun, name="Standard")
        assert profile.is_free
        assert profile.annotation == "Autogun"
        assert profile.trait_names == ["Rapid Fire (1)"]
        values = {
            stat.statline_type_stat.short_name: stat.value
            for stat in profile.statline.stats.all()
        }
        # Normalise values when storing them so display surfaces share the stat's
        # formatting.
        assert values == {
            "SR": '8"',
            "LR": '24"',
            "Str": "3",
            "AP": "-",
            "L": "1",
        }

    def test_a_second_profile_is_the_paid_ammo_line(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        _, autogun = self.make_autogun(client, weapon_statline_type)
        cursed = create_trait("Cursed")
        single_shot = create_trait("Single Shot")

        for payload in (
            {"name": "Standard", "price": "0"},
            {
                "name": "Warp round",
                "price": "10",
                "trade_point_price": "4",
                "traits": [str(cursed.pk), str(single_shot.pk)],
            },
        ):
            self.add_line(client, autogun, **payload)

        profiles = list(
            WeaponProfile.objects.filter(weapon=autogun).order_by("position")
        )
        assert [p.name for p in profiles] == ["Standard", "Warp round"]
        assert [p.price for p in profiles] == [0, 10]
        assert profiles[1].trade_point_price == 4
        assert profiles[1].trait_names == ["Cursed", "Single Shot"]

    def test_the_card_draws_what_was_authored(
        self,
        author,
        client,
        default_pack,
        weapon_statline_type,
        gang_type,
        fighter_type,
    ):
        from django.contrib.auth.models import User

        from n26.core.render import build_model_card
        from n26.core.render_text import render_model_card
        from n26.library.authoring import create_profile, create_trait, set_statline
        from n26.library.models import Weapon
        from n26.tests.sandbox.actions import (
            found_gang,
            give_weapon,
            hire,
        )

        _, autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")
        self.add_line(
            client,
            autogun,
            name="Standard",
            price="0",
            traits=[str(rapid_fire.pk)],
            short_range="8",
            long_range="24",
            strength="3",
            armour_piercing="-",
            lethality="1",
        )

        ganger = create_profile("Ganger", fighter_type, gang_type, price=50)
        set_statline(ganger, movement=5, weapon_skill=4, toughness=3)
        gang = found_gang(
            "The Authored",
            gang_type,
            owner=User.objects.create_user("gunsmith"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)
        give_weapon(fighter, Weapon.objects.get(name="Autogun"), paid=20)

        card = build_model_card(fighter)
        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Autogun" in text
        assert "Rapid Fire (1)" in text
        assert '8"' in text


class TestWeaponAccessories:
    """Accessory forms specify compatible weapon categories or asterisked weapons;
    wargear forms omit those fields.
    """

    def test_authoring_the_bracket(self, author, client, default_pack):
        from n26.library.authoring import create_category
        from n26.library.models import WeaponAccessory

        las = create_category("Ranged Weapons", "Las Weapons")
        client.post(
            "/n26/authoring/weapon-accessory/new/",
            {
                "name": "Focusing crystal",
                "price": "30",
                "trade_point_price": "1",
                "fits_category": str(las.pk),
            },
        )
        crystal = WeaponAccessory.objects.get(name="Focusing crystal")
        assert crystal.fits_category == las
        assert not crystal.fits_asterisked

    def test_the_asterisk_bracket(self, author, client, default_pack):
        from n26.library.models import WeaponAccessory

        client.post(
            "/n26/authoring/weapon-accessory/new/",
            {
                "name": "Suspensors",
                "price": "60",
                "trade_point_price": "2",
                "fits_asterisked": "on",
            },
        )
        assert WeaponAccessory.objects.get(name="Suspensors").fits_asterisked

    def test_wargear_carries_no_bracket(self, author, client, default_pack):
        from n26.library.forms import generate_form

        form = generate_form(specs()["create_wargear"])()
        assert "fits_category" not in form.fields
        assert "fits_asterisked" not in form.fields


def row_printing(body, words):
    """Return the unique table row containing the requested text, including its
    markup.
    """
    printing = [row for row in re.findall(r"<tr\b.*?</tr>", body, re.S) if words in row]
    assert len(printing) == 1, f"{len(printing)} rows print {words!r}"
    return printing[0]


# Exclude shared navigation islands when selecting the page-specific island.
PAGE_ISLAND = "[data-react-module]:not([data-react-name='quick-switcher']):not([data-react-name='account-menu'])"


def form_switches(body):
    """Decode React form-switch props in document order."""
    soup = BeautifulSoup(body, "html.parser")
    return [
        json.loads(soup.find(id=host["data-react-props"]).string)
        for host in soup.select("[data-react-module*='/form-switch-']")
    ]


def form_switch(body, name):
    matches = [props for props in form_switches(body) if props["name"] == name]
    assert matches, f"No form switch named {name}"
    return matches[0]


def island_props(body, module=None, name=None):
    """Decode props for the first matching page island, excluding shared navigation
    islands.
    """
    soup = BeautifulSoup(body, "html.parser")
    hosts = soup.select(PAGE_ISLAND)
    for host in hosts:
        if module is not None and f"{module}-" not in host["data-react-module"]:
            continue
        props = json.loads(soup.find(id=host["data-react-props"]).string)
        if name is None or props.get("name") == name:
            return props
    raise AssertionError(f"No {module or 'page'} island for {name or 'this page'}")


def island_rows(body):
    """Read authoring-list records from the page island props."""
    return island_props(body)["rows"]


def cells_of(row):
    """Read table cells in document order, excluding cells containing checkboxes."""
    return [
        cell
        for cell in re.findall(r"<td\b.*?</td>", row, re.S)
        if 'type="checkbox"' not in cell
    ]


def words_in(markup):
    """Strip markup, unescape HTML entities and normalise whitespace."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def link_words(markup):
    """Read the text of the first link."""
    return words_in(re.search(r"<a\b[^>]*>(.*?)</a>", markup, re.S).group(1))


class TestTheQualifier:
    """Qualifiers distinguish same-named content for authors without changing its
    player-facing name.
    """

    def test_two_weapons_may_share_a_printed_name(self, author, client, default_pack):
        from n26.library.models import Weapon

        for qualifier in ("Sumpkroc", "Psychoteric Wyrm"):
            client.post(
                "/n26/authoring/weapon/new/",
                {
                    "name": "Ferocious jaws",
                    "qualifier": qualifier,
                    "slots": "1",
                    "price": "0",
                    "trade_point_price": "0",
                },
            )

        both = Weapon.objects.filter(name="Ferocious jaws")
        assert both.count() == 2
        assert {str(weapon) for weapon in both} == {"Ferocious jaws"}
        assert {weapon.authoring_label for weapon in both} == {
            "Ferocious jaws — Sumpkroc",
            "Ferocious jaws — Psychoteric Wyrm",
        }

    def test_the_same_name_and_qualifier_is_still_refused(
        self, author, client, default_pack
    ):
        from n26.library.models import Subtype

        for _ in range(2):
            response = client.post(
                "/n26/authoring/subtype/new/",
                {"name": "Mounted", "qualifier": "beasts"},
            )
        assert response.status_code == 200
        assert "already exists" in response.content.decode()
        assert Subtype.objects.filter(name="Mounted").count() == 1

    def test_pickers_show_it_so_an_author_can_choose(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_subtype
        from n26.library.forms import generate_form

        create_subtype("Hardened", qualifier="Goliath")
        create_subtype("Hardened", qualifier="Escher")
        form = generate_form(specs()["ef_adds"])()
        labels = [str(label) for _, label in form.fields["thing_subtype"].choices]
        assert "Hardened — Goliath" in labels
        assert "Hardened — Escher" in labels

    def test_a_listing_links_the_name_and_says_the_qualifier_beside_it(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_weapon

        for qualifier in ("Sumpkroc", "Psychoteric Wyrm"):
            create_weapon("Ferocious jaws", qualifier=qualifier)

        body = client.get("/n26/authoring/weapon/").content.decode()
        row = next(row for row in island_rows(body) if row["qualifier"] == "Sumpkroc")

        assert row["label"] == "Ferocious jaws"
        assert row["qualifier"] == "Sumpkroc"
        assert row["url"] == f"/n26/authoring/weapon/{row['pk']}/"

    def test_the_link_still_carries_the_bracket_a_card_prints(
        self, author, client, default_pack
    ):
        """Keep the player-facing annotation inside the link and the author-only
        qualifier outside it.
        """
        from n26.library.authoring import create_wargear

        create_wargear("Ammo", annotation="5+", qualifier="Goliath")

        body = client.get("/n26/authoring/wargear/").content.decode()
        row = island_rows(body)[0]

        assert row["label"] == "Ammo (5+)"
        assert row["qualifier"] == "Goliath"

    def test_the_search_still_finds_a_row_by_it(self, author, client, default_pack):
        from n26.library.authoring import create_weapon

        create_weapon("Ferocious jaws", qualifier="Sumpkroc")

        body = client.get("/n26/authoring/weapon/").content.decode()

        assert "sumpkroc" in island_rows(body)[0]["search"]

    def test_a_carrier_table_splits_it_from_the_name_too(
        self, author, client, default_pack
    ):
        from n26.library.authoring import (
            attach_modifiers_to,
            create_subtype,
            create_weapon,
            ef_adds,
            modifier,
            targets_model,
        )

        made = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        attach_modifiers_to(
            create_weapon("Ferocious jaws", qualifier="Sumpkroc"), [made]
        )

        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()
        name_cell, _ = cells_of(row_printing(body, "Sumpkroc"))

        assert link_words(name_cell) == "Ferocious jaws"
        assert words_in(name_cell) == "Ferocious jaws — Sumpkroc"

    def test_a_carried_weapon_profile_links_to_its_own_page(
        self, author, client, default_pack
    ):
        """A weapon profile has a detail page even though it has no standalone kind
        listing.
        """
        from n26.library.authoring import (
            add_weapon_profile,
            attach_modifiers_to,
            create_subtype,
            create_weapon,
            ef_adds,
            modifier,
            targets_model,
        )

        made = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        line = add_weapon_profile(create_weapon("Autogun"), name="Warp round")
        attach_modifiers_to(line, [made])

        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert f'href="/n26/authoring/weapon-profiles/{line.pk}/"' in body

    def test_it_is_distinguished_from_the_annotation(self):
        """Field help must distinguish an author-only qualifier from a player-facing
        annotation.
        """
        from n26.library.models import Weapon

        qualifier = str(Weapon._meta.get_field("qualifier").help_text)
        annotation = str(Weapon._meta.get_field("annotation").help_text)
        assert "never by players" in qualifier
        assert "annotation instead" in qualifier
        assert "Shown in brackets after the name" in annotation


class TestAWeaponsOwnLine:
    """An unnamed weapon profile represents the weapon itself; named profiles render
    as additional lines.
    """

    def make_autogun(self, client, weapon_statline_type):
        client.post(
            "/n26/authoring/weapon/new/",
            {
                "name": "Autogun",
                "slots": "1",
                "statline_type": str(weapon_statline_type.pk),
                "price": "20",
                "trade_point_price": "0",
            },
        )
        from n26.library.models import Weapon

        return Weapon.objects.get(name="Autogun")

    def add_line(self, client, weapon, **payload):
        return client.post(
            f"/n26/authoring/weapons/{weapon.pk}/add-profile/",
            {"trade_point_price": "0", **payload},
        )

    def test_the_form_does_not_demand_one(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        body = client.get(
            f"/n26/authoring/weapons/{autogun.pk}/add-profile/"
        ).content.decode()
        # Form requiredness derives from the authoring verb.
        from n26.library.forms import generate_form

        form = generate_form(specs()["add_weapon_profile"])()
        assert not form.fields["name"].required
        assert "Leave blank for the weapon" in body

    def test_an_unnamed_line_is_the_weapon(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.models import WeaponProfile

        autogun = self.make_autogun(client, weapon_statline_type)
        response = self.add_line(
            client,
            autogun,
            price="0",
            short_range="8",
            long_range="24",
            strength="3",
            armour_piercing="-",
            lethality="1",
        )
        assert response.status_code == 302

        profile = WeaponProfile.objects.get(weapon=autogun)
        assert profile.name == ""
        assert str(profile) == "Autogun"

    def test_the_page_shows_what_was_typed(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")
        self.add_line(
            client,
            autogun,
            price="0",
            traits=[str(rapid_fire.pk)],
            short_range="8",
            long_range="24",
            strength="3",
        )

        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        line = WeaponProfile.objects.get(weapon=autogun)
        opens = f'href="/n26/authoring/weapon-profiles/{line.pk}/"'
        assert opens in body
        row = body.split(opens, 1)[1].split("</tr>", 1)[0]
        assert "Autogun" in row
        assert "own line" in row
        assert "SR 8&quot;" in row
        assert "LR 24&quot;" in row
        assert "Str 3" in row
        assert "Rapid Fire (1)" in row
        assert "free" in row

    def test_the_page_shows_a_named_line_with_its_price(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        self.add_line(
            client,
            autogun,
            name="Warp round",
            price="10",
            trade_point_price="4",
            short_range="8",
        )
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        # Inspect the profile record because field help also mentions the weapon's own
        # line.
        from n26.library.models import WeaponProfile

        line = WeaponProfile.objects.get(weapon=autogun)
        opens = f'href="/n26/authoring/weapon-profiles/{line.pk}/"'
        row = body.split(opens, 1)[1].split("</tr>", 1)[0]
        assert "Warp round" in row
        assert "+10cr" in row
        assert "own line" not in row

    def test_named_and_unnamed_lines_read_as_the_book_prints_them(
        self,
        author,
        client,
        default_pack,
        weapon_statline_type,
        gang_type,
        fighter_type,
    ):
        from django.contrib.auth.models import User

        from n26.core.render import render_gang
        from n26.core.render_text import render_model_card
        from n26.library.authoring import create_profile, create_trait, set_statline
        from n26.tests.sandbox.actions import (
            buy_weapon_profile,
            found_gang,
            give_weapon,
            hire,
        )

        autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")
        cursed = create_trait("Cursed")
        self.add_line(
            client,
            autogun,
            price="0",
            traits=[str(rapid_fire.pk)],
            short_range="8",
            long_range="24",
        )
        self.add_line(
            client,
            autogun,
            name="Warp round",
            price="10",
            trade_point_price="4",
            traits=[str(cursed.pk)],
            short_range="8",
            long_range="24",
        )

        ganger = create_profile("Ganger", fighter_type, gang_type, price=50)
        set_statline(ganger, movement=5, weapon_skill=4)
        gang = found_gang(
            "The Armed",
            gang_type,
            owner=User.objects.create_user("armourer"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)
        held = give_weapon(fighter, autogun, paid=20)
        # The unnamed profile arrives with the weapon; additional ammunition is
        # purchased.
        from n26.library.models import WeaponProfile

        buy_weapon_profile(
            held, WeaponProfile.objects.get(weapon=autogun, name="Warp round")
        )

        (card,) = render_gang(gang).models
        text = "\n".join(render_model_card(card))
        print("\n" + text)
        lines = [line.strip() for line in text.splitlines()]
        # Render the unnamed profile on the weapon's line without repeating its name
        # below.
        own = next(line for line in lines if line.startswith("Autogun"))
        assert "Rapid Fire (1)" in own
        assert "30cr" in own
        assert not any(line.startswith("- Autogun") for line in lines)
        # Additional profiles omit the weapon annotation when nested on its card.
        named = next(line for line in lines if line.startswith("- Warp round"))
        assert named.startswith("- Warp round (+10cr)")
        assert "Cursed" in named
        assert "(Autogun)" not in named


class TestCorrectingAWeaponProfile:
    """Weapon profiles have separate edit pages for names, prices, characteristics
    and traits.
    """

    def make_autogun(self, client, weapon_statline_type):
        client.post(
            "/n26/authoring/weapon/new/",
            {
                "name": "Autogun",
                "slots": "1",
                "statline_type": str(weapon_statline_type.pk),
                "price": "20",
                "trade_point_price": "0",
            },
        )
        from n26.library.models import Weapon

        return Weapon.objects.get(name="Autogun")

    def add_line(self, client, weapon, **payload):
        """Create a weapon profile through its page and return the saved profile."""
        from n26.library.models import WeaponProfile

        client.post(
            f"/n26/authoring/weapons/{weapon.pk}/add-profile/",
            {"price": "0", "trade_point_price": "0", **payload},
        )
        return WeaponProfile.objects.get(weapon=weapon, name=payload.get("name", ""))

    def test_the_weapon_page_leads_to_each_lines_own_page(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        own = self.add_line(client, autogun)
        warp = self.add_line(client, autogun, name="Warp round", price="10")

        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()

        assert f'href="/n26/authoring/weapon-profiles/{own.pk}/"' in body
        assert f'href="/n26/authoring/weapon-profiles/{warp.pk}/"' in body

    def test_the_page_opens_the_form_on_what_is_there(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        warp = self.add_line(
            client, autogun, name="Warp round", price="10", short_range="8"
        )

        body = client.get(f"/n26/authoring/weapon-profiles/{warp.pk}/").content.decode()

        assert 'value="Warp round"' in body
        assert re.search(r'name="edit-price"[^>]*value="10"', body)
        assert re.search(r'name="statline-short_range"[^>]*value="8&quot;"', body)
        assert f'href="/n26/authoring/weapon/{autogun.pk}/"' in body

    def test_a_change_to_the_name_and_the_price_is_saved(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        warp = self.add_line(client, autogun, name="Warp round", price="10")

        response = client.post(
            f"/n26/authoring/weapon-profiles/{warp.pk}/",
            {"edit-name": "Warp shell", "edit-price": "12"},
        )
        assert response.status_code == 302

        warp.refresh_from_db()
        assert (warp.name, warp.price) == ("Warp shell", 12)

        body = client.get(response["Location"]).content.decode()
        assert 'value="Warp shell"' in body
        assert re.search(r'name="edit-price"[^>]*value="12"', body)

    def test_the_characteristics_are_rewritten_and_one_can_be_emptied(
        self, author, client, default_pack, weapon_statline_type
    ):
        """Unlike blank values during creation, blank values during editing clear
        existing characteristics.
        """
        autogun = self.make_autogun(client, weapon_statline_type)
        own = self.add_line(
            client, autogun, short_range="8", long_range="24", strength="3"
        )

        client.post(
            f"/n26/authoring/weapon-profiles/{own.pk}/",
            {
                "edit-price": "0",
                "statline-short_range": "6",
                "statline-long_range": "18",
                "statline-strength": "",
            },
        )

        own.refresh_from_db()
        values = {
            stat.statline_type_stat.short_name: stat.value
            for stat in own.statline.stats.all()
        }
        assert values["SR"] == '6"'
        assert values["LR"] == '18"'
        assert values["Str"] == ""

    def test_the_traits_typed_are_the_traits_it_has(
        self, author, client, default_pack, weapon_statline_type
    ):
        """Replace the trait set so changing a trait does not retain its previous
        version.
        """
        from n26.library.authoring import create_trait

        autogun = self.make_autogun(client, weapon_statline_type)
        once = create_trait("Rapid Fire", "1")
        twice = create_trait("Rapid Fire", "2")
        own = self.add_line(client, autogun, traits=[str(once.pk)])
        assert own.trait_names == ["Rapid Fire (1)"]

        client.post(
            f"/n26/authoring/weapon-profiles/{own.pk}/",
            {"edit-price": "0", "edit-traits": [str(twice.pk)]},
        )

        assert own.trait_names == ["Rapid Fire (2)"]

    def test_the_bracket_a_named_line_prints_can_be_corrected(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        warp = self.add_line(client, autogun, name="Warp round", price="10")
        assert warp.annotation == "Autogun"

        client.post(
            f"/n26/authoring/weapon-profiles/{warp.pk}/",
            {
                "edit-name": "Warp round",
                "edit-annotation": "Autogun, hot-shot",
                "edit-price": "10",
            },
        )

        warp.refresh_from_db()
        assert warp.annotation == "Autogun, hot-shot"
        assert str(warp) == "Warp round (Autogun, hot-shot)"

    def test_a_second_nameless_line_is_refused_in_words(
        self, author, client, default_pack, weapon_statline_type
    ):
        """Only one unnamed profile may represent the weapon itself."""
        autogun = self.make_autogun(client, weapon_statline_type)
        self.add_line(client, autogun)
        warp = self.add_line(client, autogun, name="Warp round", price="10")

        response = client.post(
            f"/n26/authoring/weapon-profiles/{warp.pk}/",
            {"edit-name": "", "edit-price": "10"},
        )

        assert response.status_code == 200
        assert (
            "This weapon already has its own unnamed line" in response.content.decode()
        )
        warp.refresh_from_db()
        assert warp.name == "Warp round"

    def test_an_exclusive_line_with_a_trade_point_price_is_refused_in_words(
        self, author, client, default_pack, weapon_statline_type
    ):
        """Report incompatible exclusivity and Trading Post pricing without blaming
        the name.
        """
        autogun = self.make_autogun(client, weapon_statline_type)
        warp = self.add_line(client, autogun, name="Warp round", price="10")

        response = client.post(
            f"/n26/authoring/weapon-profiles/{warp.pk}/",
            {
                "edit-name": "Warp round",
                "edit-price": "10",
                "edit-trade_point_price": "2",
                "edit-is_exclusive": "on",
            },
        )

        assert response.status_code == 200
        body = response.content.decode()
        assert "never offered at the Trading Post" in body
        assert "unnamed line" not in body
        warp.refresh_from_db()
        assert warp.is_exclusive is False
        assert warp.trade_point_price == 0

    def test_the_page_offers_the_guns_other_lines(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        own = self.add_line(client, autogun)
        warp = self.add_line(client, autogun, name="Warp round", price="10")

        body = client.get(f"/n26/authoring/weapon-profiles/{own.pk}/").content.decode()

        assert f"/n26/authoring/weapon-profiles/{warp.pk}/" in body
        assert "Warp round (Autogun)" in body

    def test_an_unknown_line_is_a_404(self, author, client, default_pack):
        import uuid

        assert (
            client.get(f"/n26/authoring/weapon-profiles/{uuid.uuid4()}/").status_code
            == 404
        )


class TestTheWeaponProfilePageIsStaffed:
    """Weapon-profile editing requires staff access, including for signed-in users."""

    @pytest.fixture
    def line(self, default_pack):
        from n26.library.authoring import add_weapon_profile, create_weapon

        return add_weapon_profile(create_weapon("Autogun", price=20))

    def test_a_stranger_is_sent_to_log_in(self, client, line):
        response = client.get(f"/n26/authoring/weapon-profiles/{line.pk}/")
        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_a_plain_user_is_not_staff(self, client, line):
        client.force_login(User.objects.create_user("player"))
        response = client.get(f"/n26/authoring/weapon-profiles/{line.pk}/")
        assert response.status_code == 302
        assert "login" in response["Location"]


@pytest.fixture
def autogun(author, default_pack, weapon_statline_type):
    from n26.library.authoring import create_weapon

    return create_weapon("Autogun", price=20, statline_type=weapon_statline_type)


class TestAddingAWeaponProfile:
    """A separate creation page adds a weapon profile with its characteristics and
    traits.
    """

    def address(self, weapon):
        return f"/n26/authoring/weapons/{weapon.pk}/add-profile/"

    def test_the_weapon_page_offers_the_way_there_rather_than_a_form(
        self, autogun, client
    ):
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()

        assert self.address(autogun) in body
        assert "Add weapon profile" in body
        assert 'name="short_range"' not in body
        assert "Add a weapon profile" not in body

    def test_a_line_is_added_with_its_stats_and_traits(self, autogun, client):
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        rapid_fire = create_trait("Rapid Fire", "1")

        added = client.post(
            self.address(autogun),
            {
                "name": "Warp round",
                "price": "10",
                "trade_point_price": "4",
                "traits": [str(rapid_fire.pk)],
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
        )

        assert added.status_code == 302
        assert added["Location"] == f"/n26/authoring/weapon/{autogun.pk}/"

        line = WeaponProfile.objects.get(weapon=autogun, name="Warp round")
        assert (line.price, line.trade_point_price) == (10, 4)
        assert line.annotation == "Autogun"
        assert line.trait_names == ["Rapid Fire (1)"]
        assert {
            stat.statline_type_stat.short_name: stat.value
            for stat in line.statline.stats.all()
        } == {"SR": '8"', "LR": '24"', "Str": "3", "AP": "-", "L": "1"}

        body = client.get(added["Location"]).content.decode()
        assert "Added Warp round." in body
        assert f'href="/n26/authoring/weapon-profiles/{line.pk}/"' in body

    def test_untyped_characteristics_are_recorded_as_nothing(self, autogun, client):
        """Blank characteristics during creation omit the statline; blank
        characteristics during editing clear stored values.
        """
        from n26.library.models import WeaponProfile

        client.post(self.address(autogun), {"name": "Silent", "price": "0"})

        line = WeaponProfile.objects.get(weapon=autogun, name="Silent")
        assert getattr(line, "statline", None) is None

    def test_a_second_nameless_line_is_refused_in_words(self, autogun, client):
        from n26.library.authoring import add_weapon_profile
        from n26.library.models import WeaponProfile

        add_weapon_profile(autogun)

        refused = client.post(self.address(autogun), {"price": "0"})

        assert refused.status_code == 200
        assert (
            "This weapon already has its own unnamed line" in refused.content.decode()
        )
        assert WeaponProfile.objects.filter(weapon=autogun).count() == 1

    def test_an_exclusive_line_with_a_trade_point_price_is_refused_in_words(
        self, autogun, client
    ):
        """Creation and editing must report the same incompatibility between
        exclusivity and Trading Post pricing.
        """
        from n26.library.models import WeaponProfile

        refused = client.post(
            self.address(autogun),
            {
                "name": "Warp round",
                "price": "10",
                "trade_point_price": "2",
                "is_exclusive": "on",
            },
        )

        assert refused.status_code == 200
        body = refused.content.decode()
        assert "never offered at the Trading Post" in body
        assert "unnamed line" not in body
        assert not WeaponProfile.objects.filter(weapon=autogun).exists()

    def test_a_weapon_with_no_shape_says_so_instead_of_drawing_boxes(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_weapon
        from n26.library.models import WeaponProfile

        club = create_weapon("Club", price=10)

        body = client.get(self.address(club)).content.decode()
        assert "Club has no statline shape set" in body
        assert "carry no stats" in body

        client.post(self.address(club), {"name": "Two-handed", "price": "0"})
        assert WeaponProfile.objects.filter(weapon=club, name="Two-handed").exists()

    def test_an_unknown_weapon_is_a_404(self, author, client, default_pack):
        import uuid

        address = f"/n26/authoring/weapons/{uuid.uuid4()}/add-profile/"
        assert client.get(address).status_code == 404

    def test_another_kinds_page_keeps_its_own_add_form(
        self, author, client, default_pack, make_stat
    ):
        from n26.library.authoring import create_statline_type

        shape = create_statline_type("Weapon")
        make_stat("Str", "Strength")

        body = client.get(f"/n26/authoring/statline-type/{shape.pk}/").content.decode()

        assert "add-profile" not in body
        assert 'name="stat"' in body


class TestRemovingAWeaponProfile:
    """Unused weapon profiles can be deleted with their statlines; built-ins and gang
    assignments prevent deletion.
    """

    @pytest.fixture
    def own(self, autogun):
        """The unnamed weapon profile, with range and strength values."""
        from n26.library.authoring import add_weapon_profile, set_statline

        line = add_weapon_profile(autogun)
        set_statline(line, short_range=8, strength=3)
        return line

    @pytest.fixture
    def warp(self, autogun):
        from n26.library.authoring import add_weapon_profile

        return add_weapon_profile(autogun, "Warp round", price=10)

    def address(self, line):
        return f"/n26/authoring/weapon-profiles/{line.pk}/delete/"

    def test_the_weapon_page_offers_a_way_off_each_line(
        self, autogun, own, warp, client
    ):
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()

        assert self.address(own) in body
        assert self.address(warp) in body

    def test_asking_names_the_line_and_its_weapon_and_changes_nothing(
        self, autogun, warp, client
    ):
        from n26.library.models import WeaponProfile

        body = client.get(self.address(warp)).content.decode()

        assert "Delete Warp round (Autogun)?" in body
        assert "cannot undo" in body
        assert f'href="/n26/authoring/weapon/{autogun.pk}/"' in body
        assert WeaponProfile.objects.filter(pk=warp.pk).exists()

    def test_the_line_goes_and_its_characteristics_with_it(self, autogun, own, client):
        from n26.library.models import Statline, WeaponProfile

        statline = own.statline

        done = client.post(self.address(own))

        assert done["Location"] == f"/n26/authoring/weapon/{autogun.pk}/"
        assert not WeaponProfile.objects.filter(pk=own.pk).exists()
        assert not Statline.objects.filter(pk=statline.pk).exists()
        body = client.get(done["Location"]).content.decode()
        assert "Deleted Autogun." in body
        assert "None yet" in body

    def test_a_line_a_hire_comes_with_is_refused_in_words(
        self, autogun, warp, client, default_pack, gang_type, fighter_type
    ):
        """Name the referencing built-in set so an author can remove that dependency
        before deleting the profile.
        """
        from n26.library.authoring import add_built_in, create_profile
        from n26.library.models import WeaponProfile

        ganger = create_profile("Ganger", fighter_type, gang_type, price=50)
        member = add_built_in(ganger, warp)

        refused = client.post(self.address(warp), follow=True)
        body = refused.content.decode()

        assert refused.redirect_chain[-1][0] == self.address(warp)
        assert "still in use" in body
        assert f"the built-in set “{member.default_set.name}” brings" in body
        assert "Ganger built-ins" == member.default_set.name
        assert WeaponProfile.objects.filter(pk=warp.pk).exists()

    def test_a_line_a_gang_holds_is_refused_in_words(
        self, autogun, own, warp, client, default_pack, gang_type, fighter_type
    ):
        from django.contrib.auth.models import User

        from n26.library.authoring import create_profile, set_statline
        from n26.library.models import WeaponProfile
        from n26.tests.sandbox.actions import (
            buy_weapon_profile,
            found_gang,
            give_weapon,
            hire,
        )

        ganger = create_profile("Ganger", fighter_type, gang_type, price=50)
        set_statline(ganger, movement=5, weapon_skill=4)
        gang = found_gang(
            "The Armed",
            gang_type,
            owner=User.objects.create_user("armourer"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)
        held = give_weapon(fighter, autogun, paid=20)
        buy_weapon_profile(held, warp)

        refused = client.post(self.address(warp), follow=True)
        body = refused.content.decode()

        assert refused.redirect_chain[-1][0] == self.address(warp)
        assert "still in use" in body
        # Protect purchased profiles and identify the gang and model that hold them.
        assert "paid for" in body
        assert "The Armed" in body
        assert "Yolanda" in body
        assert WeaponProfile.objects.filter(pk=warp.pk).exists()

    def test_an_unknown_line_is_a_404(self, author, client, default_pack):
        import uuid

        address = f"/n26/authoring/weapon-profiles/{uuid.uuid4()}/delete/"
        assert client.get(address).status_code == 404


class TestTheWeaponProfileActPagesAreStaffed:
    """Weapon-profile creation and deletion require staff access for GET and POST
    requests.
    """

    @pytest.fixture
    def line(self, default_pack):
        from n26.library.authoring import add_weapon_profile, create_weapon

        return add_weapon_profile(create_weapon("Autogun", price=20))

    def test_a_stranger_cannot_reach_either_page(self, client, line):
        for address in (
            f"/n26/authoring/weapon-profiles/{line.pk}/delete/",
            f"/n26/authoring/weapons/{line.weapon.pk}/add-profile/",
        ):
            response = client.get(address)
            assert response.status_code == 302
            assert "login" in response["Location"]

    def test_a_plain_user_cannot_delete_a_line(self, client, line):
        from n26.library.models import WeaponProfile

        client.force_login(User.objects.create_user("player"))
        response = client.post(f"/n26/authoring/weapon-profiles/{line.pk}/delete/")

        assert response.status_code == 302
        assert "login" in response["Location"]
        assert WeaponProfile.objects.filter(pk=line.pk).exists()

    def test_a_plain_user_cannot_add_one(self, client, line):
        client.force_login(User.objects.create_user("player"))
        response = client.post(
            f"/n26/authoring/weapons/{line.weapon.pk}/add-profile/",
            {"name": "Warp round", "price": "10"},
        )

        assert response.status_code == 302
        assert "login" in response["Location"]
        assert not line.weapon.profiles.filter(name="Warp round").exists()


class TestListingsSayWhatARowIs:
    """Listings show kind-specific details and separate author help, including
    searchable notes.
    """

    def test_a_skill_shows_its_set_and_its_number(self, author, client, default_pack):
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["skills"].create()
        body = client.get("/n26/authoring/skill/").content.decode()
        assert "Catfall" in body
        assert "Agility" in body
        assert "rolled on a 1" in body

    def test_an_inherent_skill_shows_no_number(self, author, client, default_pack):
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["skills"].create()
        body = client.get("/n26/authoring/skill/").content.decode()
        row = body.split("Juggernaut", 1)[1].split("</tr>", 1)[0]
        assert "Inherent" in row
        assert "rolled on" not in row

    def test_a_priced_thing_shows_its_price(self, author, client, default_pack):
        from n26.library.authoring import create_wargear

        create_wargear("Mesh armour", price=15, trade_point_price=1)
        body = client.get("/n26/authoring/wargear/").content.decode()
        assert "15cr" in body
        assert "TP 1" in body

    def test_an_exclusive_thing_says_so_rather_than_a_number(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_wargear

        create_wargear("House gear", price=20, is_exclusive=True)
        body = client.get("/n26/authoring/wargear/").content.decode()
        assert "TP E" in body

    def test_a_row_carries_the_note_its_author_wrote(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_wargear

        create_wargear(
            "Mesh armour",
            price=15,
            library_author_help="Ask before repricing these.",
        )

        body = client.get("/n26/authoring/wargear/").content.decode()
        row = island_rows(body)[0]

        assert row["notes"] == ["15cr"]
        assert row["help"] == "Ask before repricing these."

    def test_a_row_with_no_note_says_only_what_the_kind_says(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_wargear

        create_wargear("Mesh armour", price=15)

        body = client.get("/n26/authoring/wargear/").content.decode()
        row = island_rows(body)[0]

        assert row["notes"] == ["15cr"]
        assert row["help"] == ""

    def test_the_search_finds_a_row_by_the_note(self, author, client, default_pack):
        from n26.library.authoring import create_wargear

        create_wargear(
            "Mesh armour",
            price=15,
            library_author_help="Ask before repricing these.",
        )

        body = client.get("/n26/authoring/wargear/").content.decode()

        assert "repricing" in island_rows(body)[0]["search"]

    def test_a_carrier_table_carries_the_note_too(self, author, client, default_pack):
        from n26.library.authoring import (
            attach_modifiers_to,
            create_subtype,
            create_wargear,
            ef_adds,
            modifier,
            targets_model,
        )

        made = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        attach_modifiers_to(
            create_wargear(
                "Mesh armour", library_author_help="Ask before repricing these."
            ),
            [made],
        )

        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()
        _, notes = cells_of(row_printing(body, "Mesh armour"))

        assert words_in(notes) == "wargear · Ask before repricing these."


class TestTheGangSurface:
    """Gang types, profiles and their built-ins can be created through authoring
    pages.
    """

    def make_ganger(self, client, person_type):
        from n26.library.models import GangType, Profile

        client.post(
            "/n26/authoring/gang-type/new/",
            {"name": "Escher", "starting_credits": "1000"},
        )
        escher = GangType.objects.get(name="Escher")
        response = client.post(
            "/n26/authoring/profile/new/",
            {
                "name": "Ganger",
                "profile_type": str(person_type.pk),
                "gang_type": str(escher.pk),
                "price": "50",
            },
        )
        return response, Profile.objects.get(name="Ganger")

    def test_a_gang_type_from_the_page(self, author, client, default_pack):
        from n26.library.models import GangType

        response = client.post(
            "/n26/authoring/gang-type/new/",
            {"name": "Escher", "starting_credits": "1000"},
        )
        assert response.status_code == 302
        escher = GangType.objects.get(name="Escher")
        assert escher.starting_credits == 1000
        body = client.get("/n26/authoring/gang-type/").content.decode()
        assert "founds with 1000cr" in body

    def test_creating_a_profile_lands_on_its_page(
        self, author, client, default_pack, person_type
    ):
        response, ganger = self.make_ganger(client, person_type)
        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/profile/{ganger.pk}/"
        assert ganger.price == 50
        assert ganger.profile_type == person_type

        body = client.get(response["Location"]).content.decode()
        assert "None yet" in body

    def test_granting_an_equipment_list(
        self, author, client, default_pack, person_type
    ):
        from n26.library.models import Collection

        _, ganger = self.make_ganger(client, person_type)
        client.post(
            "/n26/authoring/collection/new/", {"name": "House Escher Equipment List"}
        )
        escher_list = Collection.objects.get(name="House Escher Equipment List")

        response = client.post(
            f"/n26/authoring/profile/{ganger.pk}/",
            {
                "act": "built_in",
                "thing_kind": "collection",
                "thing_collection": str(escher_list.pk),
            },
        )
        assert response.status_code == 302

        ganger.refresh_from_db()
        member = ganger.built_in_members.get()
        assert member.assignable == escher_list

        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()
        assert "Comes with" in body
        assert "House Escher Equipment List" in body
        assert "a list it may use" in body

        listing = client.get("/n26/authoring/profile/").content.decode()
        assert "uses House Escher Equipment List" in listing
        assert "Escher" in listing

    def test_a_counter_built_in_keeps_its_opening_value(
        self, author, client, default_pack, person_type
    ):
        from n26.library.authoring import create_counter

        _, ganger = self.make_ganger(client, person_type)
        xp = create_counter("XP")

        client.post(
            f"/n26/authoring/profile/{ganger.pk}/",
            {
                "act": "built_in",
                "thing_kind": "counter",
                "thing_counter": str(xp.pk),
                "amount": "6",
            },
        )
        ganger.refresh_from_db()
        member = ganger.built_in_members.get()
        assert member.assignable == xp
        assert member.amount == 6

        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()
        assert "opening value 6" in body

    def test_the_grant_needs_a_pick(self, author, client, default_pack, person_type):
        _, ganger = self.make_ganger(client, person_type)
        response = client.post(
            f"/n26/authoring/profile/{ganger.pk}/",
            {"act": "built_in", "thing_kind": "collection"},
        )
        assert response.status_code == 200
        assert "Pick or name a collection." in response.content.decode()
        assert not ganger.built_in_members.exists()

    def test_the_page_carries_the_union_toggle(
        self, author, client, default_pack, person_type
    ):
        _, ganger = self.make_ganger(client, person_type)
        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()
        assert "data-union-kind" in body
        assert 'data-union-member="collection"' in body
        assert "syncUnionPickers" in body

    def test_the_create_page_offers_the_usual_built_ins(
        self, author, client, default_pack, person_type
    ):
        from n26.library.authoring import (
            create_collection,
            create_counter,
            create_subtype,
        )

        create_counter("XP")
        create_collection("House Escher Equipment List")
        create_subtype("Ganger")
        body = client.get("/n26/authoring/profile/new/").content.decode()
        assert "Starting XP" in body
        assert "Equipment list" in body
        assert "Subtypes" in body
        assert "blank to skip" in body

    def test_a_profile_with_its_built_ins_in_one_submit(
        self, author, client, default_pack, person_type, gang_type
    ):
        from n26.library.authoring import (
            create_collection,
            create_counter,
            create_subtype,
        )
        from n26.library.models import Profile

        xp = create_counter("XP")
        escher_list = create_collection("House Escher Equipment List")
        ganger_subtype = create_subtype("Ganger")
        specialist = create_subtype("Specialist")

        response = client.post(
            "/n26/authoring/profile/new/",
            {
                "name": "Ganger",
                "profile_type": str(person_type.pk),
                "gang_type": str(gang_type.pk),
                "price": "50",
                "suggested-starting_xp_amount": "61",
                "suggested-equipment_list": str(escher_list.pk),
                "suggested-subtypes": [str(ganger_subtype.pk), str(specialist.pk)],
            },
        )
        assert response.status_code == 302

        ganger = Profile.objects.get(name="Ganger")
        by_thing = {m.assignable: m for m in ganger.built_in_members}
        assert set(by_thing) == {xp, escher_list, ganger_subtype, specialist}
        assert by_thing[xp].amount == 61

        body = client.get(response["Location"]).content.decode()
        assert "House Escher Equipment List" in body
        assert "opening value 61" in body
        assert "Specialist" in body

    def test_skipped_suggestions_build_nothing(
        self, author, client, default_pack, person_type
    ):
        from n26.library.authoring import create_collection, create_counter

        create_counter("XP")
        create_collection("House Escher Equipment List")
        _, ganger = self.make_ganger(client, person_type)
        assert not ganger.built_in_members.exists()


class TestDeletingAThing:
    """Delete unused content while preserving dependencies and reusable modifiers."""

    def test_an_unused_affiliation_is_deleted_for_good(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_affiliation
        from n26.library.models import Affiliation

        stray = create_affiliation("Never Chosen")
        page = f"/n26/authoring/affiliation/{stray.pk}/delete/"

        asked = client.get(page).content.decode()
        assert "Delete Never Chosen?" in asked
        assert "cannot undo" in asked

        done = client.post(page)
        assert done["Location"] == "/n26/authoring/affiliation/"
        assert not Affiliation.objects.filter(pk=stray.pk).exists()

    def test_a_row_in_use_is_refused_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_affiliation, create_collection
        from n26.library.models import Affiliation

        held = create_affiliation("Clan House Outcast")
        create_collection("Affiliations", entries=[(held, {})])

        page = f"/n26/authoring/affiliation/{held.pk}/delete/"
        refused = client.post(page, follow=True)
        assert refused.redirect_chain[-1][0] == page
        assert "still in use" in refused.content.decode()
        assert Affiliation.objects.filter(pk=held.pk).exists()

    def test_a_deleted_carrier_leaves_its_reusable_modifier_behind(
        self, author, client, default_pack
    ):
        from n26.library.authoring import (
            create_rule,
            create_skill,
            ef_adds,
            targets_model,
        )
        from n26.library.authoring import modifier as compose
        from n26.library.models import Modifier, Rule

        rule = create_rule("Fleeting")
        compose(
            "Grants a skill",
            targets_model(),
            ef_adds(create_skill("Sprint")),
            attach_to=rule,
        )

        done = client.post(f"/n26/authoring/rule/{rule.pk}/delete/")
        assert done.status_code == 302
        assert not Rule.objects.filter(pk=rule.pk).exists()
        # Deleting a carrier must preserve modifiers that can be shared with other
        # carriers.
        assert Modifier.objects.filter(name="Grants a skill").exists()

    def test_the_detail_page_offers_the_way_there(self, author, client, default_pack):
        from n26.library.authoring import create_affiliation

        stray = create_affiliation("Never Chosen")
        body = client.get(f"/n26/authoring/affiliation/{stray.pk}/").content.decode()
        assert f"/n26/authoring/affiliation/{stray.pk}/delete/" in body


class TestOfferingAChoice:
    """Profile options use default sets with unique pack-level names and independent
    player-facing labels.
    """

    @pytest.fixture
    def profile(self, author, client, default_pack, person_type, gang_type):
        from n26.library.authoring import create_profile

        return create_profile("Ganger", person_type, gang_type, price=55)

    def page(self, client, profile):
        return f"/n26/authoring/profile/{profile.pk}/"

    def add_option(self, client, profile, **fields):
        return client.post(self.page(client, profile), {"act": "option", **fields})

    def test_a_profile_with_no_options_says_it_is_hired_one_way(
        self, author, client, profile
    ):
        body = client.get(self.page(client, profile)).content.decode()
        assert "Hired the same way every time." in body
        assert "Add an option to offer an alternative." in body

    def test_an_option_founds_the_set_that_holds_what_it_brings(
        self, author, client, profile
    ):
        from n26.library.authoring import create_weapon

        rifle = create_weapon("Long rifle", profiles=[("Standard", 0)])
        response = self.add_option(
            client,
            profile,
            name="with a long rifle",
            price="35",
            thing_kind="weapon",
            thing_weapon=str(rifle.pk),
        )
        assert response.status_code == 302

        option = profile.options.get()
        assert option.name == "with a long rifle"
        assert option.default_set.price == 35
        assert [m.assignable for m in option.default_set.members.all()] == [rifle]
        # Default-set names serve authors; option labels serve players and need not
        # match.
        assert option.default_set.name != option.name

    def test_a_second_thing_joins_the_option_through_its_set(
        self, author, client, profile
    ):
        from n26.library.authoring import add_default_member, create_weapon

        breath = create_weapon("Gaseous eruption breath", profiles=[("Spray", 0)])
        talons = create_weapon("Razor-sharp talons", profiles=[("Rend", 0)])
        self.add_option(
            client,
            profile,
            name="Eruption and razors",
            price="50",
            thing_kind="weapon",
            thing_weapon=str(breath.pk),
        )
        option = profile.options.get()
        add_default_member(option.default_set, talons)

        body = client.get(self.page(client, profile)).content.decode()
        assert "Gaseous eruption breath, Razor-sharp talons" in body

    def test_an_option_may_bring_nothing(self, author, client, profile):
        response = self.add_option(client, profile, name="As standard", price="0")
        assert response.status_code == 302

        option = profile.options.get()
        assert option.name == "As standard"
        assert not option.default_set.members.exists()
        assert ">nothing<" in client.get(self.page(client, profile)).content.decode()

    def test_two_profiles_may_both_offer_as_standard(
        self, author, client, profile, person_type, gang_type
    ):
        """Default-set names are unique within a pack; player-facing option names may
        repeat across profiles.
        """
        from n26.library.authoring import create_profile

        other = create_profile("Juve", person_type, gang_type, price=25)
        self.add_option(client, profile, name="As standard", price="0")
        response = self.add_option(client, other, name="As standard", price="0")
        assert response.status_code == 302

        assert profile.options.get().name == other.options.get().name == "As standard"
        assert profile.options.get().default_set != other.options.get().default_set

    def test_the_options_with_no_set_are_the_main_pick(self, author, client, profile):
        self.add_option(client, profile, name="As standard", price="0")
        self.add_option(client, profile, name="with a long rifle", price="35")

        (group, options), *rest = profile.grouped_offers()
        assert group is None and not rest
        # The first option is the group's default selection.
        assert [option.name for option in options] == [
            "As standard",
            "with a long rifle",
        ]
        body = client.get(self.page(client, profile)).content.decode()
        assert "One of the following" in body
        assert "the first is what you get" in body

    def test_a_further_set_is_made_and_then_filled(self, author, client, profile):
        from n26.library.models import OptionGroup

        response = client.post(
            self.page(client, profile),
            {"act": "option-set", "name": "Additional grenades", "choose": "any"},
        )
        assert response.status_code == 302
        grenades = OptionGroup.objects.get(name="Additional grenades")
        assert grenades.carrier == profile
        assert grenades.choose == "any"

        self.add_option(
            client, profile, name="Choke gas", price="50", group=str(grenades.pk)
        )
        option = profile.options.get()
        assert option.group == grenades

        body = client.get(self.page(client, profile)).content.decode()
        assert "Any of the following" in body
        assert "Additional grenades" in body
        assert "players never see it" in body
        assert "Choke gas" in body

    def test_an_add_control_pins_the_set_it_was_clicked_on(
        self, author, client, profile
    ):
        """Carry the selected option group in the URL and name it on the form."""
        from n26.library.authoring import create_option_group

        grenades = create_option_group(profile, "Extra grenades", choose="any")

        body = client.get(self.page(client, profile)).content.decode()
        assert f"?set={grenades.pk}#add-option" in body

        pinned = client.get(
            f"{self.page(client, profile)}?set={grenades.pk}"
        ).content.decode()
        assert "This option joins Extra grenades — any of the following." in pinned

        plain = client.get(self.page(client, profile)).content.decode()
        assert "This option joins the main pick" in plain

    def test_a_forged_set_from_another_profile_is_refused(
        self, author, client, profile, person_type, gang_type
    ):
        """Validate group ownership even when a submission bypasses the offered
        choices.
        """
        from n26.library.authoring import create_option_group, create_profile

        mine = create_option_group(profile, "Melee weapons")
        other = create_profile("Juve", person_type, gang_type, price=25)
        theirs = create_option_group(other, "Somebody else's pick")

        body = client.get(self.page(client, profile)).content.decode()
        assert "Melee weapons" in body
        assert "Somebody else's pick" not in body

        response = self.add_option(
            client, profile, name="Stray", price="0", group=str(theirs.pk)
        )
        assert response.status_code == 200
        assert not profile.options.exists()
        assert mine.options.count() == 0

    def test_an_option_is_withdrawn_from_a_page_of_its_own(
        self, author, client, profile
    ):
        from n26.library.authoring import create_weapon
        from n26.library.models import DefaultAssignmentSet

        rifle = create_weapon("Long rifle", profiles=[("Standard", 0)])
        self.add_option(
            client,
            profile,
            name="with a long rifle",
            price="35",
            thing_kind="weapon",
            thing_weapon=str(rifle.pk),
        )
        option = profile.options.get()
        gathered = option.default_set.pk

        asked = client.get(f"/n26/authoring/options/{option.pk}/remove/")
        assert asked.status_code == 200
        body = asked.content.decode()
        assert "Stop offering with a long rifle?" in body
        assert "Long rifle" in body
        assert profile.options.exists()

        done = client.post(f"/n26/authoring/options/{option.pk}/remove/")
        assert done["Location"] == self.page(client, profile)
        assert not profile.options.exists()
        # Remove the option's generated default set while preserving the referenced
        # weapon.
        assert not DefaultAssignmentSet.objects.filter(pk=gathered).exists()
        rifle.refresh_from_db()

    def test_an_option_grows_a_second_item_through_its_own_page(
        self, author, client, profile
    ):
        from n26.library.authoring import create_weapon

        create_weapon("Shock baton", profiles=[("Standard", 0)])
        claw = create_weapon("Assault claw", profiles=[("Standard", 0)])
        self.add_option(
            client,
            profile,
            name="Claw and baton",
            price="20",
            thing_kind="weapon",
            thing_weapon=str(claw.pk),
        )
        option = profile.options.get()

        page = client.get(f"/n26/authoring/options/{option.pk}/add/").content.decode()
        assert "Add to Claw and baton" in page
        assert "Already brings: Assault claw" in page

        from n26.library.models import Weapon

        baton = Weapon.objects.get(name="Shock baton")
        done = client.post(
            f"/n26/authoring/options/{option.pk}/add/",
            {"thing_kind": "weapon", "thing_weapon": str(baton.pk)},
        )
        assert done.status_code == 302
        assert [m.assignable.name for m in option.default_set.members.all()] == [
            "Assault claw",
            "Shock baton",
        ]
        body = client.get(self.page(client, profile)).content.decode()
        assert "Assault claw, Shock baton" in body

    def test_a_set_may_offer_one_or_none(self, author, client, profile):
        from n26.library.models import OptionGroup

        response = client.post(
            self.page(client, profile),
            {"act": "option-set", "name": "A grenade", "choose": "one-or-none"},
        )
        assert response.status_code == 302
        assert OptionGroup.objects.get(name="A grenade").choose == "one-or-none"

        body = client.get(self.page(client, profile)).content.decode()
        assert "One of the following, or none" in body

    def test_removing_a_set_takes_its_options_with_it(self, author, client, profile):
        from n26.library.authoring import create_option_group
        from n26.library.models import Option, OptionGroup

        grenades = create_option_group(profile, "Additional grenades", choose="any")
        self.add_option(
            client, profile, name="Choke gas", price="50", group=str(grenades.pk)
        )
        self.add_option(
            client, profile, name="Stun", price="30", group=str(grenades.pk)
        )

        body = client.get(
            f"/n26/authoring/option-sets/{grenades.pk}/remove/"
        ).content.decode()
        assert "Stop offering these options?" in body
        assert "Choke gas" in body
        assert "Stun" in body

        done = client.post(f"/n26/authoring/option-sets/{grenades.pk}/remove/")
        assert done["Location"] == self.page(client, profile)
        assert not OptionGroup.objects.filter(pk=grenades.pk).exists()
        assert not Option.objects.filter(profile=profile).exists()

    def test_what_was_authored_here_is_what_a_hire_screen_offers(
        self, author, client, profile
    ):
        from n26.core.hire import build_hire_entry
        from n26.library.authoring import create_option_group, create_wargear

        self.add_option(client, profile, name="As standard", price="0")
        self.add_option(
            client,
            profile,
            name="with a long rifle",
            price="35",
            thing_kind="wargear",
            thing_wargear=str(create_wargear("Long rifle").pk),
        )
        grenades = create_option_group(profile, "Additional grenades", choose="any")
        self.add_option(
            client,
            profile,
            name="Choke gas grenades",
            price="50",
            group=str(grenades.pk),
        )

        entry = build_hire_entry(profile)
        assert [option.name for option in entry.options] == [
            "As standard",
            "with a long rifle",
        ]
        assert entry.base_price == 55
        assert [group.choose for group in entry.groups] == ["one", "any"]
        assert [option.name for option in entry.groups[1].options] == [
            "Choke gas grenades"
        ]
        assert entry.groups[1].options[0].total_price == 105


class TestTheCollectionPage:
    """Collection details show definitions and previews built from the player-facing
    browse structure.
    """

    def test_creating_a_collection_lands_on_its_page(
        self, author, client, default_pack
    ):
        from n26.library.models import Collection

        response = client.post("/n26/authoring/collection/new/", {"name": "House List"})
        made = Collection.objects.get(name="House List")
        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/collection/{made.pk}/"

        body = client.get(response["Location"]).content.decode()
        assert "Nothing defined yet" in body
        assert "Empty — nothing matches the definition yet" in body

    def test_a_collection_is_given_its_position_on_the_page(
        self, author, client, default_pack
    ):
        from n26.library.models import Collection

        page = client.get("/n26/authoring/collection/new/").content.decode()
        assert 'name="position"' in page
        assert "The lowest number comes first, and Equip opens on it." in page

        response = client.post(
            "/n26/authoring/collection/new/",
            {"name": "Chaos Corrupted Equipment List", "position": "100"},
        )
        assert response.status_code == 302
        made = Collection.objects.get(name="Chaos Corrupted Equipment List")
        assert made.position == 100

        response = client.post(
            "/n26/authoring/collection/new/", {"name": "Escher Equipment List"}
        )
        assert response.status_code == 302
        assert Collection.objects.get(name="Escher Equipment List").position == 0

    def test_a_negative_position_is_refused_in_words(
        self, author, client, default_pack
    ):
        from n26.library.models import Collection

        response = client.post(
            "/n26/authoring/collection/new/",
            {"name": "Sup-Pets Equipment List", "position": "-1"},
        )
        assert response.status_code == 200
        assert "greater than or equal to 0" in response.content.decode()
        assert not Collection.objects.filter(name="Sup-Pets Equipment List").exists()

    def test_the_trading_post_previews_its_membership(
        self, author, client, default_pack
    ):
        from n26.library.authoring import (
            add_weapon_profile,
            create_category,
            create_weapon,
        )
        from n26.library.models import Collection
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["trading-post"].create()
        guns = create_category("Ranged Weapons", "Auto/Stub Weapons")
        boltgun = create_weapon("Boltgun", price=55, trade_point_price=3, category=guns)
        add_weapon_profile(boltgun, name="Kraken round", price=15, trade_point_price=5)
        create_weapon("House-pattern needler", price=40, category=guns)

        post = Collection.objects.get(name="Trading Post")
        body = client.get(f"/n26/authoring/collection/{post.pk}/").content.decode()

        assert "every weapon with a TP price" in body
        assert "every wargear with a TP price" in body
        assert "Boltgun" in body
        assert "Kraken round" in body
        # Exclude select options because the entry picker intentionally offers content
        # outside the preview.
        import re

        outside_pickers = re.sub(r"<select[\s\S]*?</select>", "", body)
        assert "House-pattern needler" not in outside_pickers
        assert "Ranged Weapons" in body

    def test_an_entry_is_added_priced_and_removed_through_the_page(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_collection, create_wargear
        from n26.library.models import CollectionEntry, Wargear

        blade = create_wargear("Escher blade", price=15)
        house_list = create_collection("House Escher Equipment List")
        page = f"/n26/authoring/collection/{house_list.pk}/"

        response = client.post(
            page,
            {
                "act": "entry",
                "thing_kind": "wargear",
                "thing_wargear": str(blade.pk),
                "price_override": "10",
            },
        )
        assert response.status_code == 302
        entry = CollectionEntry.objects.get(collection=house_list)
        assert entry.assignable == blade
        assert entry.price_override == 10

        body = client.get(page).content.decode()
        assert "10cr here" in body

        done = client.post(f"/n26/authoring/entries/{entry.pk}/remove/")
        assert done["Location"] == page
        assert not CollectionEntry.objects.filter(collection=house_list).exists()
        assert Wargear.objects.filter(pk=blade.pk).exists()

    def test_a_second_default_section_is_refused_in_words(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_collection

        picks = create_collection("Affiliations")
        page = f"/n26/authoring/collection/{picks.pk}/"

        first = client.post(
            page, {"act": "section", "name": "Affiliations", "is_default": "on"}
        )
        assert first.status_code == 302
        again = client.post(
            page, {"act": "section", "name": "Another", "is_default": "on"}
        )
        assert again.status_code == 200
        assert "already has a default section" in again.content.decode()
        assert picks.sections.count() == 1

    def test_the_preview_files_the_unplaced_under_the_default_section(
        self, author, client, default_pack
    ):
        """Place uncategorised entries under the collection's default section."""
        from n26.library.authoring import (
            add_section,
            create_affiliation,
            create_collection,
        )

        picks = create_collection(
            "Affiliations", entries=[(create_affiliation("Clanless Outcast"), {})]
        )
        add_section(picks, "Affiliations", is_default=True)

        body = client.get(f"/n26/authoring/collection/{picks.pk}/").content.decode()
        assert "(no section)" not in body
        assert "Clanless Outcast" in body

    def test_a_menu_asks_for_no_prices_and_prints_none(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_affiliation, create_collection
        from n26.library.models import CollectionEntry

        menu = create_collection(
            "Affiliations",
            prices_its_entries=False,
            entries=[(create_affiliation("Clanless Outcast"), {})],
        )
        page = f"/n26/authoring/collection/{menu.pk}/"

        body = client.get(page).content.decode()
        assert "Price override" not in body
        assert "Trade point override" not in body
        headings = {
            heading.get_text(" ", strip=True).casefold()
            for heading in BeautifulSoup(body, "html.parser").find_all("th")
        }
        assert "credits" not in headings
        assert "asks for nothing but the item" in body

        made = client.post(
            page,
            {
                "act": "entry",
                "thing_kind": "affiliation",
                "thing_affiliation": str(create_affiliation("Mutant Outcast").pk),
            },
        )
        assert made.status_code == 302
        assert CollectionEntry.objects.filter(collection=menu).count() == 2

    def test_the_collection_is_edited_on_its_own_page(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_collection
        from n26.library.models import Collection

        listing = create_collection("House Escher Equipment List")
        page = f"/n26/authoring/collection/{listing.pk}/"

        saved = client.post(
            page,
            {
                "act": "edit",
                "edit-name": "House Escher Armoury",
                "edit-qualifier": "",
                "edit-library_author_help": "",
            },
        )
        assert saved.status_code == 302
        listing.refresh_from_db()
        assert listing.name == "House Escher Armoury"
        # An omitted pricing checkbox on an edit disables entry pricing.
        assert listing.prices_its_entries is False
        assert Collection.objects.filter(name="House Escher Armoury").exists()

    def test_the_affiliation_pick_list_is_buildable_end_to_end(
        self, author, client, default_pack, gang_type, owner
    ):
        """Create a gang-level choice through authoring pages and verify the player
        picker offers both authored options.
        """
        from n26.core.render import render_gang
        from n26.library.models import Hidden, Pickable, Picklist, Slot, SlotType
        from n26.tests.sandbox.actions import found_gang

        client.post(
            "/n26/authoring/slot-type/new/",
            {"name": "Affiliation", "plural_name": "Affiliations"},
        )
        slot_type = SlotType.objects.get(name="Affiliation")
        page = f"/n26/authoring/slot-type/{slot_type.pk}/"
        for name in ("Clanless Outcast", "Clan House Outcast"):
            made = client.post(page, {"act": "pickable", "name": name, "qualifier": ""})
            assert made.status_code == 302
        client.post(page, {"act": "picklist", "name": "Affiliations"})
        picks = Picklist.objects.get(name="Affiliations")
        for name in ("Clanless Outcast", "Clan House Outcast"):
            added = client.post(
                f"/n26/authoring/picklist/{picks.pk}/",
                {
                    "pickable": str(Pickable.objects.get(name=name).pk),
                    "label_override": "",
                    "position": "0",
                },
            )
            assert added.status_code == 302
        client.post(
            page,
            {
                "act": "slot",
                "name": "Affiliation",
                "picklist": str(picks.pk),
                "label": "Affiliation",
                "min_picks": "0",
                "max_picks": "1",
                "assigned_to": "gang",
                "position": "0",
            },
        )
        slot = Slot.objects.get(name="Affiliation")

        client.post("/n26/authoring/hidden/new/", {"name": "Affiliation"})
        hidden = Hidden.objects.get(name="Affiliation")
        composed = client.post(
            f"/n26/authoring/hidden/{hidden.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_gang",
                "effect_kind": "ef_adds",
                "what-thing_kind": "slot",
                "what-thing_slot": str(slot.pk),
                "conditions-TOTAL_FORMS": "0",
                "conditions-INITIAL_FORMS": "0",
                "conditions-MIN_NUM_FORMS": "0",
                "conditions-MAX_NUM_FORMS": "1000",
            },
        )
        assert composed.status_code == 302

        aboard = client.post(
            f"/n26/authoring/gang-type/{gang_type.pk}/",
            {
                "act": "built_in",
                "thing_kind": "hidden",
                "thing_hidden": str(hidden.pk),
            },
        )
        assert aboard.status_code == 302

        gang_type.refresh_from_db()
        gang = found_gang("The Unmade", gang_type, owner=owner)
        line = next(
            choice
            for choice in render_gang(gang).choices
            if choice.kind_label == "Affiliation"
        )
        client.force_login(owner)
        picker = client.get(f"/n26/gangs/{gang.pk}/choose/{line.key}/").content.decode()
        assert "Clanless Outcast" in picker
        assert "Clan House Outcast" in picker

    def test_membership_by_criteria_updates_itself(self, author, client, default_pack):
        from n26.library.models import Collection
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["trading-post"].create()
        post = Collection.objects.get(name="Trading Post")
        page = f"/n26/authoring/collection/{post.pk}/"
        assert "Lasgun" not in client.get(page).content.decode()

        client.post(
            "/n26/authoring/weapon/new/",
            {"name": "Lasgun", "slots": "1", "price": "15", "trade_point_price": "1"},
        )
        assert "Lasgun" in client.get(page).content.decode()

    def test_a_curated_list_shows_entries_and_their_overrides(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_collection, create_wargear

        mesh = create_wargear("Mesh Armour", price=15, trade_point_price=1)
        heirloom = create_wargear(
            "House Heirloom Blade-Charm", price=40, is_exclusive=True
        )
        house_list = create_collection(
            "House List",
            entries=[(mesh, {"price_override": 10}), heirloom],
        )

        body = client.get(
            f"/n26/authoring/collection/{house_list.pk}/"
        ).content.decode()
        assert "10cr here" in body
        assert "priced by this list" in body
        assert ">E<" in body


class TestTheModifierSection:
    """Carrier pages expose modifiers, shared attachments and composer controls;
    foundation pages omit them.
    """

    #: Management fields for an empty condition formset, as submitted by the browser.
    NO_CONDITIONS = {
        "conditions-TOTAL_FORMS": "0",
        "conditions-INITIAL_FORMS": "0",
        "conditions-MIN_NUM_FORMS": "0",
        "conditions-MAX_NUM_FORMS": "1000",
    }

    @pytest.fixture
    def rule(self, author, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Immovable Brutes")

    def test_a_carrier_kind_gets_a_page_with_the_section(
        self, rule, client, default_pack
    ):
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "does nothing special until" in body
        props = island_props(body, "modifier-kind-picker")
        assert props["scope"]["name"] == "scope_kind"

    def test_a_foundation_kind_has_a_page_without_one(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_stat

        stat = create_stat("M", "Movement", is_inches=True)
        response = client.get(f"/n26/authoring/stat/{stat.pk}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert 'name="edit-full_name"' in body
        assert 'name="scope_kind"' not in body

    def test_step_two_renders_the_panes_the_kinds_call_for(
        self, rule, client, default_pack
    ):
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_changes_stat"
        ).content.decode()
        assert 'name="what-stat"' in body
        assert 'name="what-amount"' in body
        # Model scopes have no other fields; their condition forms supply the optional
        # narrowing.
        assert "Add a condition" in body

    def test_composing_attaches_here(self, rule, client, default_pack):
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.NO_CONDITIONS,
            },
        )
        assert response.status_code == 302

        (modifier,) = rule.modifiers.all()
        assert str(modifier.effect) == "adds Mounted"
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "adds Mounted" in body

    def test_a_condition_narrows_the_scope(self, rule, client, default_pack):
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        mounted = create_subtype("Mounted")
        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.NO_CONDITIONS,
                "conditions-TOTAL_FORMS": "1",
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
            },
        )
        assert response.status_code == 302
        (modifier,) = rule.modifiers.all()
        assert "Champion" in str(modifier.scope)

    def test_adding_a_condition_is_a_link_not_a_widget(
        self, rule, client, default_pack
    ):
        """Carry empty condition forms in the query string so they survive a refresh."""
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_adds&chips=1"
        ).content.decode()
        assert 'name="conditions-0-kind"' in body
        assert "chips=2" in body

    def test_an_incompatible_pair_refuses_in_words(self, rule, client, default_pack):
        from n26.library.authoring import create_trait

        melee = create_trait("Melee")
        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "trait",
                "what-thing_trait": str(melee.pk),
                **self.NO_CONDITIONS,
            },
        )
        assert response.status_code == 200
        assert "cannot apply" in response.content.decode()
        assert rule.modifiers.count() == 0

    def test_attach_existing_then_detach(self, rule, client, default_pack):
        from n26.library.authoring import (
            attach_modifiers_to,
            create_hidden,
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        shared = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        other = create_hidden("Corruption token")
        attach_modifiers_to(other, [shared])

        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {"act": "attach", "modifier": str(shared.pk)},
        )
        assert response.status_code == 302
        assert list(rule.modifiers.all()) == [shared]

        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "also on 1 other carrier" in body

        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {"act": "detach", "modifier": str(shared.pk)},
        )
        assert response.status_code == 302
        assert rule.modifiers.count() == 0
        assert list(other.modifiers.all()) == [shared]

    def _compose_on_rule(self, rule, client, reusable):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier

        mounted = create_subtype("Mounted")
        data = {
            "act": "compose",
            "scope_kind": "targets_model",
            "effect_kind": "ef_adds",
            "what-thing_kind": "subtype",
            "what-thing_subtype": str(mounted.pk),
            **self.NO_CONDITIONS,
        }
        if reusable:
            data["make_reusable"] = "on"
        response = client.post(f"/n26/authoring/rule/{rule.pk}/", data)
        assert response.status_code == 302
        return Modifier.objects.get()

    def test_reusable_names_it_generically_and_still_attaches(
        self, rule, client, default_pack
    ):
        """The reusable flag changes naming without changing which carrier receives
        the modifier.
        """
        made = self._compose_on_rule(rule, client, reusable=True)

        assert rule.modifiers.count() == 1
        assert str(rule) not in made.name

    def test_named_for_its_carrier_when_it_is_not_reusable(
        self, rule, client, default_pack
    ):
        made = self._compose_on_rule(rule, client, reusable=False)

        assert rule.modifiers.count() == 1
        assert made.name.startswith(f"{rule}: ")

    def test_the_weapon_page_keeps_its_parts_and_gains_the_section(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_weapon

        gun = create_weapon("Autogun", statline_type=weapon_statline_type)
        body = client.get(f"/n26/authoring/weapon/{gun.pk}/").content.decode()
        assert f"/n26/authoring/weapons/{gun.pk}/add-profile/" in body
        assert "does nothing special until" in body


class TestTheModifiersPage:
    """The modifier listing shows effect descriptions and carrier counts, with a link
    to a separate creation page.
    """

    def test_it_lists_every_modifier_with_its_reach(self, author, client, default_pack):
        from n26.library.authoring import (
            attach_modifiers_to,
            create_rule,
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        shared = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        attach_modifiers_to(create_rule("Cutter"), [shared])
        modifier("Grants Wyrd", targets_model(), ef_adds(create_subtype("Wyrd")))

        body = client.get("/n26/authoring/modifiers/").content.decode()
        rows = island_rows(body)
        mounted = next(row for row in rows if row["label"] == "Grants Mounted")
        reusable = next(row for row in rows if row["label"] == "Grants Wyrd")
        assert "adds Mounted" in mounted["notes"]
        assert "on 1 carrier" in mounted["notes"]
        assert "reusable — attached nowhere yet" in reusable["notes"]
        assert mounted["url"] == f"/n26/authoring/modifiers/{shared.pk}/"
        assert mounted["pk"] == str(shared.pk)

    def test_an_empty_page_stays_cotton(self, author, client, default_pack):
        body = client.get("/n26/authoring/modifiers/").content.decode()

        assert "None yet — the New modifier button makes the first one." in body
        assert not BeautifulSoup(body, "html.parser").select(PAGE_ISLAND)

    def test_it_offers_the_way_in_at_the_top(self, author, client, default_pack):
        body = client.get("/n26/authoring/modifiers/").content.decode()

        assert "/n26/authoring/modifiers/new/" in body
        assert "New modifier" in body

    def test_it_carries_no_composer(self, author, client, default_pack):
        body = client.get("/n26/authoring/modifiers/").content.decode()

        assert 'name="scope_kind"' not in body
        assert 'name="effect_kind"' not in body

    def test_more_modifiers_do_not_mean_more_queries(
        self, author, client, default_pack, django_assert_num_queries
    ):
        """Descriptions and carrier counts must load without a query per modifier."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import (
            attach_modifiers_to,
            create_rule,
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        def compose(name):
            made = modifier(name, targets_model(), ef_adds(create_subtype(name)))
            attach_modifiers_to(create_rule(f"{name} rule"), [made])

        for index in range(3):
            compose(f"Grants {index}")
        with CaptureQueriesContext(connection) as few:
            assert client.get("/n26/authoring/modifiers/").status_code == 200

        for index in range(3, 12):
            compose(f"Grants {index}")
        with django_assert_num_queries(len(few), exact=False):
            assert client.get("/n26/authoring/modifiers/").status_code == 200

    def test_the_facets_cost_the_page_nothing(
        self, author, client, default_pack, django_assert_num_queries
    ):
        """Derive facet options from loaded data without a query per modifier or
        kind.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def grow(indices):
            for index in indices:
                make_assorted_modifiers(f"Set {index}")

        grow(range(3))
        with CaptureQueriesContext(connection) as few:
            assert client.get("/n26/authoring/modifiers/").status_code == 200

        grow(range(3, 12))
        with django_assert_num_queries(len(few), exact=False):
            assert client.get("/n26/authoring/modifiers/").status_code == 200


class TestComposingOnItsOwnPage:
    """Standalone composition creates an unattached modifier using scope and effect
    kinds selected in the URL.
    """

    def test_the_button_reaches_a_page_that_composes(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/modifiers/new/").content.decode()
        props = island_props(body, "modifier-kind-picker")

        assert props["scope"]["name"] == "scope_kind"
        assert props["effect"]["name"] == "effect_kind"

    def test_the_two_steps_ride_the_url(self, author, client, default_pack):
        """Keep selected kinds and empty condition forms in the query string so
        composition survives a refresh.
        """
        body = client.get(
            "/n26/authoring/modifiers/new/"
            "?scope_kind=targets_weapons&effect_kind=ef_adds&chips=1"
        ).content.decode()

        assert 'name="what-thing_kind"' in body
        assert 'name="conditions-0-kind"' in body
        assert "chips=2" in body
        # Without a carrier, naming cannot switch between carrier-specific and reusable
        # forms.
        assert 'name="make_reusable"' not in body
        assert "modifier-naming-" not in body

    def test_a_modifier_can_be_made_here_and_attaches_nowhere(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier
        from n26.library.views import _carrier_count

        mounted = create_subtype("Mounted")
        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **TestTheModifierSection.NO_CONDITIONS,
            },
        )

        assert response.status_code == 302
        (made,) = Modifier.objects.all()
        assert _carrier_count(made) == 0
        assert response["Location"] == f"/n26/authoring/modifiers/{made.pk}/"
        assert made.name in client.get(response["Location"]).content.decode()

    @pytest.mark.parametrize("effect_kind", ["ef_adds", "ef_removes"])
    def test_the_composer_can_give_or_take_wargear(
        self, author, client, default_pack, effect_kind
    ):
        from n26.library.authoring import create_wargear
        from n26.library.models import Modifier

        rig = create_wargear("Drop rig", price=10)
        url = "/n26/authoring/modifiers/new/"
        body = client.get(
            url, {"scope_kind": "targets_model", "effect_kind": effect_kind}
        ).content.decode()
        assert 'value="wargear"' in body
        response = client.post(
            url,
            {
                "scope_kind": "targets_model",
                "effect_kind": effect_kind,
                "what-thing_kind": "wargear",
                "what-thing_wargear": str(rig.pk),
                **TestTheModifierSection.NO_CONDITIONS,
            },
        )
        assert response.status_code == 302
        (made,) = Modifier.objects.all()
        assert made.effect.thing == rig
        assert "Drop rig" in client.get(response["Location"]).content.decode()

    def test_the_listing_shows_what_was_made(self, author, client, default_pack):
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                "name": "Grants Mounted",
                **TestTheModifierSection.NO_CONDITIONS,
            },
        )

        body = client.get("/n26/authoring/modifiers/").content.decode()
        assert "Grants Mounted" in body

    def test_a_refusal_stays_on_the_page_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_trait

        melee = create_trait("Melee")
        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "trait",
                "what-thing_trait": str(melee.pk),
                **TestTheModifierSection.NO_CONDITIONS,
            },
        )

        assert response.status_code == 200
        assert "cannot apply" in response.content.decode()

    def test_a_duplicate_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier

        mounted = create_subtype("Mounted")
        made = {
            "scope_kind": "targets_model",
            "effect_kind": "ef_adds",
            "what-thing_kind": "subtype",
            "what-thing_subtype": str(mounted.pk),
            "name": "Grants Mounted",
            **TestTheModifierSection.NO_CONDITIONS,
        }
        client.post("/n26/authoring/modifiers/new/", made)
        response = client.post("/n26/authoring/modifiers/new/", made)

        assert response.status_code == 200
        assert "already exists in this pack" in response.content.decode()
        assert Modifier.objects.filter(name="Grants Mounted").count() == 1


def make_assorted_modifiers(prefix, client=None):
    """Create three modifiers spanning different scope, effect and attachment states.

    Names include the supplied prefix so several sets can exercise listing facets.
    """
    from n26.library.authoring import (
        attach_modifiers_to,
        create_rule,
        create_stat,
        create_subtype,
        create_trait,
        ef_adds,
        ef_changes_stat,
        modifier,
        targets_model,
        targets_weapons,
    )

    strength = create_stat(f"S{prefix}", f"Strength {prefix}")
    carried = modifier(
        f"{prefix} grants a subtype",
        targets_model(),
        ef_adds(create_subtype(f"{prefix} subtype")),
    )
    attach_modifiers_to(create_rule(f"{prefix} rule"), [carried])
    modifier(
        f"{prefix} arms every weapon",
        targets_weapons(),
        ef_adds(create_trait(f"{prefix} trait")),
    )
    modifier(
        f"{prefix} worsens a stat",
        targets_model(),
        ef_changes_stat(strength, "worsen", 1),
    )


class TestTheButtonThatChangesTheModifierType:
    """The kind picker receives the served scope and effect pair and a submit label
    for its page context.
    """

    @staticmethod
    def props(body):
        return island_props(body, "modifier-kind-picker")

    @pytest.fixture
    def carrier(self, author, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Berserker")

    def test_it_is_named_for_what_it_fetches(self, author, client, default_pack):
        body = client.get("/n26/authoring/modifiers/new/").content.decode()

        assert self.props(body)["submitLabel"] == "Continue →"

    def test_it_receives_the_pair_the_page_is_drawn_from(
        self, author, client, default_pack
    ):
        body = client.get(
            "/n26/authoring/modifiers/new/?scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        assert self.props(body)["served"] == {
            "scope": "targets_model",
            "effect": "ef_adds",
        }

    def test_a_page_drawn_from_no_kinds_matches_nothing_the_pickers_hold(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/modifiers/new/").content.decode()

        assert self.props(body)["served"] == {"scope": "", "effect": ""}

    def test_a_kind_that_is_not_one_cannot_break_out_of_the_wiring(
        self, author, client, default_pack
    ):
        """Treat kind values from the URL as data in application/json props,
        including script-like input.
        """
        body = client.get(
            "/n26/authoring/modifiers/new/"
            "?scope_kind=%27%2Balert%281%29%2B%27&effect_kind=ef_adds"
        ).content.decode()

        assert self.props(body)["served"]["scope"] == "'+alert(1)+'"
        soup = BeautifulSoup(body, "html.parser")
        host = next(
            tag
            for tag in soup.select("[data-react-module]")
            if "modifier-kind-picker-" in tag["data-react-module"]
        )
        assert soup.find(id=host["data-react-props"])["type"] == "application/json"

    def test_a_carriers_page_invites_rather_than_offers_a_change(self, carrier, client):
        body = client.get(f"/n26/authoring/rule/{carrier.pk}/").content.decode()

        assert self.props(body)["submitLabel"] == "Configure new modifier"


class TestTheKindCards:
    """Scope and effect cards explain their behaviour, examples and compatibility
    restrictions.
    """

    @pytest.fixture
    def carrier(self, author, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Berserker")

    def test_each_kind_is_a_card_with_its_words(self, author, client, default_pack):
        body = client.get("/n26/authoring/modifiers/new/").content.decode()
        props = island_props(body, "modifier-kind-picker")
        scopes = props["scope"]["cards"]
        effects = props["effect"]["cards"]

        assert props["scope"]["name"] == "scope_kind"
        assert props["effect"]["name"] == "effect_kind"
        assert {card["label"] for card in scopes} >= {
            "The model carrying it",
            "All models in the gang",
            "The gang carrying it and all models",
            "The gang carrying it",
        }
        deprecated = next(card for card in scopes if card["deprecated"])
        assert "in a different way per effect. Use with care." in (
            deprecated["description"] + deprecated["example"]
        )
        choice = next(
            card for card in effects if "choice into a section" in card["label"]
        )
        assert "the player picks" in choice["description"]
        assert "pick Ferocity and Ferocity" in choice["example"]

    def test_the_cards_still_answer_to_the_selects_field_names(
        self, author, client, default_pack
    ):
        """Select the scope and effect cards named in the URL."""
        page = client.get(
            "/n26/authoring/modifiers/new/"
            "?scope_kind=targets_model&effect_kind=ef_changes_stat"
        )
        assert page.status_code == 200
        props = island_props(page.content.decode(), "modifier-kind-picker")
        assert (
            next(card for card in props["scope"]["cards"] if card["checked"])["value"]
            == "targets_model"
        )
        assert (
            next(card for card in props["effect"]["cards"] if card["checked"])["value"]
            == "ef_changes_stat"
        )

    def test_a_carrier_that_is_never_fitted_greys_the_attached_scope(
        self, carrier, client
    ):
        """Disable an attached-weapon scope for a rule and supply the incompatibility
        reason.
        """
        body = client.get(f"/n26/authoring/rule/{carrier.pk}/").content.decode()

        props = island_props(body, "modifier-kind-picker")
        gate = next(
            card
            for card in props["scope"]["cards"]
            if card["value"] == "targets_attached_weapon"
        )
        assert gate["disabled"] is True
        assert gate["reason"] == "A special rule is never fitted to a weapon."

    def test_an_accessory_is_offered_the_attached_scope(self, author, client):
        from n26.library.authoring import create_weapon_accessory

        sight = create_weapon_accessory("Telescopic Sight")
        body = client.get(
            f"/n26/authoring/weapon-accessory/{sight.pk}/"
        ).content.decode()

        props = island_props(body, "modifier-kind-picker")
        gate = next(
            card
            for card in props["scope"]["cards"]
            if card["value"] == "targets_attached_weapon"
        )
        assert gate["disabled"] is False

    def test_every_effect_card_says_what_it_can_apply_to(
        self, author, client, default_pack
    ):
        """Supply each effect's accepted targets so the client can disable
        incompatible choices.
        """
        from n26.library.forms import EFFECT_CAN_TARGET

        body = client.get("/n26/authoring/modifiers/new/").content.decode()
        props = island_props(body, "modifier-kind-picker")
        accepts = {card["value"]: card["accepts"] for card in props["effect"]["cards"]}
        assert accepts == {
            name: list(kinds) for name, kinds in EFFECT_CAN_TARGET.items()
        }


class TestFindingAModifierAmongHundreds:
    """The modifier listing supplies search text and facet values for filtering
    loaded content in the browser.
    """

    @pytest.fixture
    def assorted(self, author, default_pack):
        make_assorted_modifiers("Alpha")
        make_assorted_modifiers("Beta")

    def facets(self, client):
        """Read facet data prepared for each modifier in the listing."""
        response = client.get("/n26/authoring/modifiers/")
        return [row["facets"] for row in response.context["rows"]]

    def options(self, client, name):
        """Read a facet menu's options in display order."""
        response = client.get("/n26/authoring/modifiers/")
        return response.context[f"{name}_options"]

    def test_there_is_a_search_and_a_menu_per_facet(self, assorted, client):
        props = island_props(client.get("/n26/authoring/modifiers/").content.decode())

        assert len(props["scopeOptions"]) == 2
        assert len(props["effectOptions"]) == 2
        assert len(props["carriedOptions"]) == 2

    def test_the_page_hands_every_rows_facets_to_the_browser(self, assorted, client):
        body = client.get("/n26/authoring/modifiers/").content.decode()
        props = island_props(body)

        assert len(props["rows"]) == 6
        assert any(row["facets"]["scope"] == "targets_weapons" for row in props["rows"])
        assert 'x-init="register(facets)"' not in body

    def test_every_row_carries_what_the_search_reads(self, assorted, client):
        """Combine lowercased names and descriptions for substring matching in the
        browser.
        """
        haystacks = [row["search"] for row in self.facets(client)]

        assert any("alpha grants a subtype" in hay for hay in haystacks)
        assert any("adds alpha subtype" in hay for hay in haystacks)

    def test_a_search_that_names_a_carrier_state_finds_it(self, assorted, client):
        haystacks = [row["search"] for row in self.facets(client)]

        assert any("reusable — attached nowhere yet" in hay for hay in haystacks)
        assert any("on 1 carrier" in hay for hay in haystacks)

    def test_every_row_says_which_scope_and_effect_it_is(self, assorted, client):
        rows = self.facets(client)

        assert {row["scope"] for row in rows} == {
            "targets_model",
            "targets_weapons",
        }
        assert {row["effect"] for row in rows} == {"ef_adds", "ef_changes_stat"}

    def test_every_row_says_whether_anything_holds_it(self, assorted, client):
        rows = self.facets(client)

        assert {row["carried"] for row in rows} == {"carried", "uncarried"}
        assert sum(row["carried"] == "carried" for row in rows) == 2

    def test_each_facet_offers_the_values_the_rows_hold(self, assorted, client):
        assert [option["value"] for option in self.options(client, "scope")] == [
            "targets_model",
            "targets_weapons",
        ]
        assert [option["value"] for option in self.options(client, "effect")] == [
            "ef_adds",
            "ef_changes_stat",
        ]
        assert [option["value"] for option in self.options(client, "carried")] == [
            "carried",
            "uncarried",
        ]

    def test_a_facet_offers_nothing_the_page_does_not_have(
        self, author, client, default_pack
    ):
        """Supply only facet values present in the current results."""
        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        modifier("Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted")))

        assert [option["value"] for option in self.options(client, "scope")] == [
            "targets_model"
        ]
        body = client.get("/n26/authoring/modifiers/").content.decode()
        props = island_props(body)
        assert len(props["scopeOptions"]) == 1
        assert len(props["effectOptions"]) == 1

    def test_the_menus_are_named_as_the_composer_names_them(self, assorted, client):
        """Use composer labels to distinguish scope verbs that share a model."""
        by_value = {
            option["value"]: option["label"]
            for option in self.options(client, "scope") + self.options(client, "effect")
        }

        assert by_value["targets_model"] == "The model carrying it"
        assert by_value["targets_weapons"] == "The model's weapons"
        assert by_value["ef_changes_stat"] == "Changes a stat"

    def test_every_verb_wears_its_own_card_label(self, author, client, default_pack):
        """Key facets by authoring verb so scopes and placement effects sharing a
        model remain distinct.
        """
        from n26.library.authoring import (
            create_category,
            create_collection,
            create_rule,
            create_trait,
            ef_adds,
            ef_places,
            ef_places_choice,
            modifier,
            targets_attached_weapon,
            targets_every_model,
            targets_gang,
            targets_gang_alone,
            targets_model,
            targets_weapons,
        )
        from n26.tests.sandbox.actions import section_of

        scopes = {
            "targets_model": targets_model(),
            "targets_every_model": targets_every_model(),
            "targets_weapons": targets_weapons(),
            "targets_attached_weapon": targets_attached_weapon(),
            "targets_gang": targets_gang(),
            "targets_gang_alone": targets_gang_alone(),
        }
        for name, scope in scopes.items():
            thing = (
                create_trait(f"For {name}")
                if name in ("targets_weapons", "targets_attached_weapon")
                else create_rule(f"For {name}")
            )
            modifier(f"Via {name}", scope, ef_adds(thing))
        collection = create_collection("Skills & Powers")
        tier = section_of(collection, "Primary", 0, is_default=True)
        family = create_category("Skills", "Combat")
        modifier("Placed outright", targets_model(), ef_places(family, tier))
        modifier("Placed as chosen", targets_model(), ef_places_choice(tier))

        by_value = {
            option["value"]: option["label"]
            for option in self.options(client, "scope") + self.options(client, "effect")
        }
        assert by_value["targets_model"] == "The model carrying it"
        assert by_value["targets_every_model"] == "All models in the gang"
        assert by_value["targets_weapons"] == "The model's weapons"
        assert by_value["targets_attached_weapon"] == "The weapon it's fitted to"
        assert by_value["targets_gang"] == "The gang carrying it and all models"
        assert by_value["targets_gang_alone"] == "The gang carrying it"
        assert by_value["ef_places"] == "Puts a category into a section"
        assert by_value["ef_places_choice"] == "Puts the player's choice into a section"

    def test_the_two_gang_reaches_filter_apart(self, author, client, default_pack):
        from n26.library.authoring import (
            create_rule,
            ef_adds,
            modifier,
            targets_gang,
            targets_gang_alone,
        )

        both = modifier("Gang rule", targets_gang(), ef_adds(create_rule("Loud")))
        alone = modifier(
            "Quiet rule", targets_gang_alone(), ef_adds(create_rule("Quiet"))
        )

        response = client.get("/n26/authoring/modifiers/")
        facets = {row["pk"]: row["facets"]["scope"] for row in response.context["rows"]}
        assert facets[both.pk] == "targets_gang"
        assert facets[alone.pk] == "targets_gang_alone"
        by_value = {o["value"]: o["label"] for o in self.options(client, "scope")}
        assert by_value["targets_gang"] == "The gang carrying it and all models"
        assert by_value["targets_gang_alone"] == "The gang carrying it"

    def test_the_readout_counts_what_was_rendered(self, assorted, client):
        response = client.get("/n26/authoring/modifiers/")

        assert response.context["count"] == 6
        assert len(island_rows(response.content.decode())) == 6

    def test_a_page_of_hundreds_still_reads_flat(
        self, author, client, default_pack, django_assert_num_queries
    ):
        """Client-side filtering loads all modifiers, so query counts must not
        increase with their number.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        def grow(indices):
            for index in indices:
                modifier(
                    f"Grants {index}",
                    targets_model(),
                    ef_adds(create_subtype(f"Subtype {index}")),
                )

        grow(range(20))
        with CaptureQueriesContext(connection) as few:
            assert client.get("/n26/authoring/modifiers/").status_code == 200

        grow(range(20, 200))
        with django_assert_num_queries(len(few), exact=False):
            response = client.get("/n26/authoring/modifiers/")
        assert response.context["count"] == 200


def drawn_picked(body, value):
    """Check whether an option has the selected attribute, allowing multiline markup."""
    return (
        re.search(rf'<option\s+value="{re.escape(str(value))}"[^>]*\sselected', body)
        is not None
    )


class TestAModifiersOwnPage:
    """Editing a shared modifier changes every carrier; deleting it detaches every
    carrier and removes its component records.
    """

    #: Management fields for a prefilled condition formset with count initial forms.
    @staticmethod
    def chips(count=0):
        return {
            "conditions-TOTAL_FORMS": str(count),
            "conditions-INITIAL_FORMS": str(count),
            "conditions-MIN_NUM_FORMS": "0",
            "conditions-MAX_NUM_FORMS": "1000",
        }

    @pytest.fixture
    def mounted(self, author, default_pack):
        from n26.library.authoring import create_subtype

        return create_subtype("Mounted")

    @pytest.fixture
    def shared(self, mounted):
        """One modifier attached to two carriers."""
        from n26.library.authoring import (
            attach_modifiers_to,
            create_rule,
            ef_adds,
            modifier,
            targets_model,
        )

        made = modifier("Grants Mounted", targets_model(), ef_adds(mounted))
        carriers = [create_rule("Beast Handler"), create_rule("Outrider")]
        for carrier in carriers:
            attach_modifiers_to(carrier, [made])
        return made, carriers

    def test_the_listing_leads_to_it(self, shared, client):
        made, _ = shared
        body = client.get("/n26/authoring/modifiers/").content.decode()
        assert f"/n26/authoring/modifiers/{made.pk}/" in body

    def test_the_page_says_what_carries_it_and_how_many(self, shared, client):
        made, _ = shared
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert "2 things carry this modifier" in body
        assert "Beast Handler" in body
        assert "Outrider" in body

    def test_the_page_states_the_settled_kinds_in_their_own_words(self, shared, client):
        """Explain immutable scope and effect kinds beside the editable fields."""
        made, _ = shared
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert "The model carrying it" in body
        assert "Only the model this is directly assigned to" in body
        assert "Gives something" in body
        assert "The target gains a subtype" in body

    def test_a_modifier_nothing_carries_says_so(self, mounted, client):
        from n26.library.authoring import ef_adds, modifier, targets_model

        made = modifier("Spare", targets_model(), ef_adds(mounted))
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert "Nothing carries this yet" in body
        assert "things carry this modifier" not in body

    def test_the_form_opens_on_what_the_modifier_says(self, shared, client):
        """Preselect both the union kind and its referenced content when editing an
        effect.
        """
        made, _ = shared
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert 'value="Grants Mounted"' in body
        assert drawn_picked(body, "subtype")
        assert drawn_picked(body, made.effect.subtype_id)

    def test_an_edit_reaches_every_carrier(self, shared, client, default_pack):
        from n26.library.authoring import create_subtype

        made, carriers = shared
        wyrd = create_subtype("Wyrd")
        response = client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Grants Wyrd",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(wyrd.pk),
                **self.chips(),
            },
        )
        assert response.status_code == 302

        for carrier in carriers:
            (held,) = carrier.modifiers.all()
            assert held.pk == made.pk
            assert held.name == "Grants Wyrd"
            assert str(held.effect) == "adds Wyrd"

    def test_the_old_parts_do_not_linger(self, shared, client, default_pack):
        from n26.library.authoring import create_subtype
        from n26.library.models import AddsAssignable, TargetsMiniature

        made, _ = shared
        wyrd = create_subtype("Wyrd")
        client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Grants Wyrd",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(wyrd.pk),
                **self.chips(),
            },
        )

        assert TargetsMiniature.objects.count() == 1
        assert AddsAssignable.objects.count() == 1

    def test_the_kinds_are_not_up_for_grabs(self, shared, client, default_pack):
        """Ignore posted scope or effect kinds because they are immutable on this
        edit page.
        """
        from n26.library.models import TargetsMiniature

        made, _ = shared
        response = client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Grants Mounted",
                "scope_kind": "targets_gang",
                "effect_kind": "ef_requires_companions",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(made.effect.subtype_id),
                **self.chips(),
            },
        )
        assert response.status_code == 302

        made.refresh_from_db()
        assert isinstance(made.scope, TargetsMiniature)
        assert str(made.effect) == "adds Mounted"

    def test_a_condition_is_shown_changed_and_taken_off(
        self, mounted, client, default_pack
    ):
        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            has_subtypes,
            modifier,
            targets_model,
        )

        champion = create_subtype("Champion")
        leader = create_subtype("Leader")
        made = modifier(
            "Mounted champions",
            targets_model(has_subtypes(champion)),
            ef_adds(mounted),
        )

        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()
        assert drawn_picked(body, champion.pk)

        client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Mounted leaders",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(leader.pk)],
            },
        )
        made.refresh_from_db()
        assert "Leader" in str(made.scope)

        # Removal changes the draft form; saving the resulting form persists the
        # condition change.
        removed = client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Mounted leaders",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(leader.pk)],
                "drop_condition": "0",
            },
        )
        assert removed.status_code == 302
        made.refresh_from_db()
        assert "Leader" in str(made.scope)
        assert "conditions-TOTAL_FORMS=0" in removed.url
        assert not drawn_picked(client.get(removed.url).content.decode(), leader.pk)

        client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Mounted leaders",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(0),
            },
        )
        made.refresh_from_db()
        assert str(made.scope) == "the model"

    def test_a_weapon_scopes_trait_reads_back_as_a_chip(
        self, author, client, default_pack
    ):
        """Restore weapon-scope trait conditions from their stored column into the
        condition form.
        """
        from n26.library.authoring import create_stat as make_stat
        from n26.library.authoring import (
            create_trait,
            ef_changes_stat,
            has_traits,
            modifier,
            targets_weapons,
        )

        melee = create_trait("Melee")
        strength = make_stat("S", "Strength")
        made = modifier(
            "Sharpened",
            targets_weapons(has_traits(melee)),
            ef_changes_stat(strength, mode="improve", amount=1),
        )

        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()
        assert drawn_picked(body, melee.pk)

        client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Sharpened",
                "what-stat": str(strength.pk),
                "what-mode": "improve",
                "what-amount": "2",
                **self.chips(1),
                "conditions-0-kind": "has_traits",
                "conditions-0-traits": [str(melee.pk)],
            },
        )
        made.refresh_from_db()
        assert str(made.scope) == "weapons with Melee"
        assert made.effect.amount == 2

    def test_a_duplicate_name_refuses_in_words(self, shared, client, default_pack):
        from n26.library.authoring import ef_adds, modifier, targets_model

        made, _ = shared
        modifier("Taken", targets_model(), ef_adds(made.effect.subtype))
        response = client.post(
            f"/n26/authoring/modifiers/{made.pk}/",
            {
                "name": "Taken",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(made.effect.subtype_id),
                **self.chips(),
            },
        )

        assert response.status_code == 200
        assert "already exists in this pack" in response.content.decode()
        made.refresh_from_db()
        assert made.name == "Grants Mounted"

    def test_asking_to_delete_changes_nothing(self, shared, client):
        from n26.library.models import AddsAssignable, Modifier, TargetsMiniature

        made, carriers = shared
        response = client.get(f"/n26/authoring/modifiers/{made.pk}/delete/")

        assert response.status_code == 200
        body = response.content.decode()
        assert "2 things carry this modifier" in body
        assert "Beast Handler" in body

        assert Modifier.objects.count() == 1
        assert TargetsMiniature.objects.count() == 1
        assert AddsAssignable.objects.count() == 1
        assert all(carrier.modifiers.count() == 1 for carrier in carriers)

    def test_deleting_takes_it_off_every_carrier_and_leaves_nothing_behind(
        self, mounted, client, default_pack
    ):
        from n26.library.authoring import (
            attach_modifiers_to,
            create_rule,
            create_subtype,
            ef_adds,
            has_subtypes,
            modifier,
            targets_model,
        )
        from n26.library.models import (
            AddsAssignable,
            HasSubtypes,
            Modifier,
            TargetsMiniature,
        )

        champion = create_subtype("Champion")
        made = modifier(
            "Mounted champions",
            targets_model(has_subtypes(champion)),
            ef_adds(mounted),
        )
        carriers = [create_rule("Beast Handler"), create_rule("Outrider")]
        for carrier in carriers:
            attach_modifiers_to(carrier, [made])

        response = client.post(f"/n26/authoring/modifiers/{made.pk}/delete/")
        assert response.status_code == 302

        assert Modifier.objects.count() == 0
        assert all(carrier.modifiers.count() == 0 for carrier in carriers)
        # Delete unreferenced scope, effect and condition records with their modifier.
        assert TargetsMiniature.objects.count() == 0
        assert AddsAssignable.objects.count() == 0
        assert HasSubtypes.objects.count() == 0

    def test_deleting_leaves_what_the_effect_named_alone(self, shared, client):
        from n26.library.models import Subtype

        made, _ = shared
        client.post(f"/n26/authoring/modifiers/{made.pk}/delete/")

        assert Subtype.objects.filter(name="Mounted").count() == 1

    def test_the_carrier_page_still_detaches_rather_than_deletes(self, shared, client):
        """Detaching changes one carrier; deleting removes the modifier from every
        carrier.
        """
        made, carriers = shared
        here, other = carriers
        client.post(
            f"/n26/authoring/rule/{here.pk}/",
            {"act": "detach", "modifier": str(made.pk)},
        )

        assert here.modifiers.count() == 0
        assert list(other.modifiers.all()) == [made]

    def test_the_page_says_what_the_modifier_does(self, shared, client):
        made, _ = shared
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert "What it does" in body
        assert "They gain the Mounted subtype, while they have it." in body

    def test_it_does_not_say_the_carriers_a_second_time(self, shared, client):
        made, _ = shared
        body = client.get(f"/n26/authoring/modifiers/{made.pk}/").content.decode()

        assert "Referenced by" not in body
        assert "Carried by the Beast Handler special rule." not in body

    def test_more_carriers_do_not_mean_more_queries(
        self, mounted, client, default_pack, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import (
            attach_modifiers_to,
            create_rule,
            ef_adds,
            modifier,
            targets_model,
        )

        made = modifier("Grants Mounted", targets_model(), ef_adds(mounted))

        def grow(indices):
            for index in indices:
                attach_modifiers_to(create_rule(f"Rule {index}"), [made])

        grow(range(3))
        with CaptureQueriesContext(connection) as few:
            assert client.get(f"/n26/authoring/modifiers/{made.pk}/").status_code == 200
        grow(range(3, 12))
        with django_assert_num_queries(len(few), exact=False):
            assert client.get(f"/n26/authoring/modifiers/{made.pk}/").status_code == 200


class TestTheModifierPagesAreStaffed:
    """Modifier creation, editing and deletion require staff access for GET and POST
    requests.
    """

    @pytest.fixture
    def made(self, author, default_pack, client):
        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        row = modifier(
            "Grants Mounted", targets_model(), ef_adds(create_subtype("Mounted"))
        )
        client.logout()
        return row

    @pytest.fixture
    def addresses(self, made):
        return [
            "/n26/authoring/modifiers/new/",
            f"/n26/authoring/modifiers/{made.pk}/",
            f"/n26/authoring/modifiers/{made.pk}/delete/",
        ]

    def test_anonymous_is_sent_to_log_in(self, addresses, client):
        for address in addresses:
            response = client.get(address)
            assert response.status_code == 302, address
            assert "login" in response["Location"]

    def test_a_plain_user_is_refused(self, addresses, client):
        client.force_login(User.objects.create_user("player"))
        for address in addresses:
            response = client.get(address)
            assert response.status_code == 302, address
            assert "login" in response["Location"], address

    def test_a_plain_user_cannot_post_either(self, addresses, made, client):
        from n26.library.models import Modifier

        client.force_login(User.objects.create_user("player"))
        for address in addresses:
            assert client.post(address, {}).status_code == 302, address
        assert Modifier.objects.count() == 1


class TestAuthoringPagesDoNotScaleQueriesWithContent:
    """Query counts must not increase when content or related records are added.

    Exercise labels, built-ins, statlines and placement descriptions that traverse
    related data.
    """

    def assert_flat(self, client, url, grow, django_assert_num_queries):
        """Measure query counts before and after growing the fixture; reject an
        increase.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        grow(range(3))
        with CaptureQueriesContext(connection) as few:
            assert client.get(url).status_code == 200
        grow(range(3, 12))
        with django_assert_num_queries(len(few), exact=False):
            assert client.get(url).status_code == 200

    def test_the_profile_listing_reads_flat_however_many_profiles(
        self,
        author,
        client,
        default_pack,
        person_type,
        gang_type,
        django_assert_num_queries,
    ):
        """Resolve equipment-list access through prefetched built-ins rather than
        per-profile queries.
        """
        from n26.library.authoring import (
            add_built_in,
            create_collection,
            create_profile,
        )

        house_list = create_collection("House List")

        def grow(indices):
            for index in indices:
                profile = create_profile(f"Fighter {index}", person_type, gang_type)
                add_built_in(profile, house_list)

        self.assert_flat(
            client, "/n26/authoring/profile/", grow, django_assert_num_queries
        )

    def test_the_category_listing_and_a_category_page_read_flat(
        self, author, client, default_pack, django_assert_num_queries
    ):
        import itertools

        from n26.library.authoring import create_category, create_section

        fresh = itertools.count()
        made = []

        def grow(indices):
            for _ in indices:
                index = next(fresh)
                section = create_section(f"Section {index}", position=index)
                made.append(create_category(section, f"Category {index}"))

        grow(range(3))
        first = made[0]
        self.assert_flat(
            client,
            f"/n26/authoring/category/{first.pk}/",
            grow,
            django_assert_num_queries,
        )
        self.assert_flat(
            client, "/n26/authoring/category/", grow, django_assert_num_queries
        )

    def test_a_weapon_page_reads_flat_however_many_profiles(
        self, author, client, default_pack, django_assert_num_queries
    ):
        from n26.library.authoring import (
            add_weapon_profile,
            create_stat,
            create_statline_type,
            create_trait,
            create_weapon,
            set_statline,
        )

        shape = create_statline_type(
            "Ranged", stats=[create_stat("R", "Range", is_inches=True)]
        )
        weapon = create_weapon("Gun", statline_type=shape)
        rapid = create_trait("Rapid Fire")

        def grow(indices):
            for index in indices:
                line = add_weapon_profile(
                    weapon, f"ammo {index}", price=5, traits=[rapid]
                )
                set_statline(line, range=8)

        self.assert_flat(
            client,
            f"/n26/authoring/weapon/{weapon.pk}/",
            grow,
            django_assert_num_queries,
        )

    def test_a_statline_shape_page_reads_flat_however_many_stats(
        self, author, client, default_pack, django_assert_num_queries
    ):
        from n26.library.authoring import (
            add_stat_to_statline_type,
            create_stat,
            create_statline_type,
        )

        shape = create_statline_type("Vehicle")

        def grow(indices):
            for index in indices:
                add_stat_to_statline_type(
                    shape, create_stat(f"S{index}", f"Stat {index}")
                )

        self.assert_flat(
            client,
            f"/n26/authoring/statline-type/{shape.pk}/",
            grow,
            django_assert_num_queries,
        )

    def test_a_profile_page_reads_flat_however_many_built_ins(
        self,
        author,
        client,
        default_pack,
        person_type,
        gang_type,
        django_assert_num_queries,
    ):
        from n26.library.authoring import add_built_in, create_profile, create_wargear

        profile = create_profile("Champion", person_type, gang_type)

        def grow(indices):
            for index in indices:
                add_built_in(profile, create_wargear(f"Kit {index}"))

        self.assert_flat(
            client,
            f"/n26/authoring/profile/{profile.pk}/",
            grow,
            django_assert_num_queries,
        )

    def test_a_collection_page_reads_flat_however_many_entries(
        self, author, client, default_pack, django_assert_num_queries
    ):
        from n26.library.authoring import create_collection, create_wargear

        collection = create_collection("House List")

        def grow(indices):
            from n26.library.models import CollectionEntry

            for index in indices:
                CollectionEntry.objects.create(
                    collection=collection,
                    assignable=create_wargear(f"Ware {index}"),
                    position=index,
                )

        self.assert_flat(
            client,
            f"/n26/authoring/collection/{collection.pk}/",
            grow,
            django_assert_num_queries,
        )

    def test_placement_modifiers_do_not_mean_more_queries(
        self, author, client, default_pack, django_assert_num_queries
    ):
        """Placement descriptions traverse the section and its collection without
        adding queries per modifier.
        """
        from n26.library.authoring import (
            attach_modifiers_to,
            create_category,
            create_collection,
            create_rule,
            create_section,
            ef_places,
            modifier,
            section_of,
            targets_model,
        )

        collection = create_collection("Skills & Powers")
        tier = section_of(collection, "Primary", 0)

        def grow(indices):
            for index in indices:
                section = create_section(f"Section {index}", position=index)
                made = modifier(
                    f"Places {index}",
                    targets_model(),
                    ef_places(create_category(section, f"Cat {index}"), tier),
                )
                attach_modifiers_to(create_rule(f"Rule {index}"), [made])

        self.assert_flat(
            client, "/n26/authoring/modifiers/", grow, django_assert_num_queries
        )


class TestRemovingABuiltIn:
    """A carrier's built-ins can be taken back off, one line at a time.

    What goes is the membership. The thing named stays in the library,
    the carrier's other lines stay, and models hired before the removal
    keep what they were hired with — built-ins are materialised at the
    moment of hiring and nothing retracts them, so a removal reaches
    future hires only.
    """

    @pytest.fixture
    def ganger(self, author, default_pack, person_type, gang_type):
        """A fighter entry coming with a list, a gun and the gun's ammo."""
        from n26.library.authoring import (
            add_built_in,
            create_collection,
            create_profile,
            create_weapon,
        )

        profile = create_profile("Ganger", person_type, gang_type, price=50)
        autogun = create_weapon("Autogun", profiles=[("", 0), ("Warp round", 10)])
        add_built_in(profile, create_collection("House Escher Equipment List"))
        add_built_in(profile, autogun)
        add_built_in(profile, autogun.profiles.get(name="Warp round"))
        profile.refresh_from_db()
        return profile

    def address(self, member):
        return f"/n26/authoring/built-ins/{member.pk}/remove/"

    def test_the_profile_page_offers_a_way_off_each_line(self, ganger, client):
        member = ganger.built_in_members.get(collection__isnull=False)
        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()

        assert self.address(member) in body
        # And the section says which of the two acts that control is.
        assert "the thing itself stays in the library" in body

    def test_asking_changes_nothing(self, ganger, client):
        member = ganger.built_in_members.get(collection__isnull=False)
        response = client.get(self.address(member))

        assert response.status_code == 200
        body = response.content.decode()
        assert "House Escher Equipment List" in body
        assert "stays in the library" in body
        assert ganger.built_in_members.count() == 3

    def test_removing_takes_off_exactly_that_line(self, ganger, client):
        from n26.library.models import Collection

        member = ganger.built_in_members.get(collection__isnull=False)
        response = client.post(self.address(member))

        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/profile/{ganger.pk}/"
        assert not ganger.built_in_members.filter(collection__isnull=False).exists()
        # The gun and its ammo are untouched, and so is the list itself:
        # it is content of its own, and only the line naming it went.
        assert ganger.built_in_members.count() == 2
        assert Collection.objects.filter(name="House Escher Equipment List").exists()

    def test_ammo_goes_with_its_gun(self, ganger, client):
        """A weapon profile in the set arrives stacked on the weapon
        coming in the same hire. Left behind it would name a gun nothing
        brings, which refuses at the moment of hiring."""
        from n26.library.models import WeaponProfile

        member = ganger.built_in_members.get(weapon__isnull=False)
        client.post(self.address(member))

        assert [str(row.assignable) for row in ganger.built_in_members] == [
            "House Escher Equipment List"
        ]
        # Both of the weapon's lines are still in the library.
        assert WeaponProfile.objects.filter(weapon__name="Autogun").count() == 2

    def test_the_page_names_what_goes_with_the_gun(self, ganger, client):
        member = ganger.built_in_members.get(weapon__isnull=False)
        body = client.get(self.address(member)).content.decode()

        assert "These go with it" in body
        assert "Warp round" in body

    def test_a_set_two_things_come_with_names_them_both(
        self, ganger, client, person_type, gang_type
    ):
        """Nothing makes a set of defaults belong to one carrier, so the
        page asks who holds it rather than assuming."""
        from n26.library.authoring import create_profile

        juve = create_profile("Juve", person_type, gang_type)
        juve.built_ins = ganger.built_ins
        juve.save()

        member = ganger.built_in_members.get(collection__isnull=False)
        body = client.get(self.address(member)).content.decode()
        assert "More than one thing comes with this set" in body
        assert "Juve" in body

        response = client.post(self.address(member))
        # No one page to return to when several things hold the set.
        assert response["Location"] == "/n26/authoring/"
        assert not juve.built_in_members.filter(collection__isnull=False).exists()

    def test_a_model_hired_before_the_removal_keeps_its_kit(
        self, ganger, client, gang_type
    ):
        from n26.core.models import Assignment
        from n26.core.reconcile import assert_reconciled
        from n26.tests.sandbox.actions import found_gang, hire

        gang = found_gang(
            "The Bad Girls",
            gang_type,
            owner=User.objects.create_user("player-owner"),
            budget=1000,
        )
        early = hire(gang, ganger, "Early")

        member = ganger.built_in_members.get(weapon__isnull=False)
        client.post(self.address(member))

        late = hire(gang, ganger, "Late")
        assert Assignment.objects.filter(
            miniature=early, weapon__name="Autogun"
        ).exists()
        assert not Assignment.objects.filter(
            miniature=late, weapon__name="Autogun"
        ).exists()
        assert_reconciled(gang)

    def test_a_stranger_is_sent_to_log_in(self, ganger, client):
        member = ganger.built_in_members.get(collection__isnull=False)
        client.logout()
        response = client.get(self.address(member))

        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_a_plain_user_is_refused_and_cannot_post(self, ganger, client):
        member = ganger.built_in_members.get(collection__isnull=False)
        client.force_login(User.objects.create_user("player"))

        assert client.get(self.address(member)).status_code == 302
        assert client.post(self.address(member), {}).status_code == 302
        assert ganger.built_in_members.count() == 3


class TestAnythingCanComeWithSomething:
    """Coming with something is not a fighter entry's privilege.

    ``built_ins`` is a column on the assignable mixin, so a piece of
    wargear that always arrives with a weapon — a beast and its claws —
    is as ordinary as a fighter and their equipment list. The pages have
    to offer it wherever the model allows it, or a rule that works
    perfectly well cannot be written down.
    """

    @pytest.fixture
    def beast(self, author, default_pack):
        from n26.library.authoring import create_wargear

        return create_wargear("Dustback Helamite", price=45)

    @pytest.fixture
    def claws(self, author, default_pack):
        from n26.library.authoring import create_weapon

        return create_weapon("Helamite claws", profiles=[("", 0)])

    def address(self, thing):
        return f"/n26/authoring/wargear/{thing.pk}/"

    def test_a_wargear_can_be_given_a_weapon_from_its_own_page(
        self, beast, claws, client
    ):
        added = client.post(
            self.address(beast),
            {"act": "built_in", "thing_kind": "weapon", "thing_weapon": str(claws.pk)},
        )

        assert added.status_code == 302
        beast.refresh_from_db()
        assert [str(row.assignable) for row in beast.built_in_members] == [
            "Helamite claws"
        ]

    def test_and_the_page_then_says_what_it_comes_with(self, beast, claws, client):
        client.post(
            self.address(beast),
            {"act": "built_in", "thing_kind": "weapon", "thing_weapon": str(claws.pk)},
        )
        body = client.get(self.address(beast)).content.decode()

        assert "Comes with" in body
        assert "Helamite claws" in body

    def test_a_carrier_coming_with_nothing_says_so_rather_than_hiding(
        self, beast, client
    ):
        body = client.get(self.address(beast)).content.decode()

        assert "Comes with" in body
        assert "None yet" in body

    def test_the_words_do_not_name_the_one_carrier_they_started_on(self, beast, client):
        """A fighter entry is hired and a piece of wargear is bought, so
        the section cannot describe itself as something a hire gets."""
        body = client.get(self.address(beast)).content.decode()

        assert "the moment it is acquired" in body
        assert "hire of this profile" not in body

    def test_the_line_can_be_taken_off_again(self, beast, claws, client):
        from n26.library.authoring import add_built_in

        member = add_built_in(beast, claws)
        beast.refresh_from_db()

        asked = client.get(f"/n26/authoring/built-ins/{member.pk}/remove/")
        assert asked.status_code == 200
        # The page names the thing holding the set, which is not a
        # profile and must still be found and linked.
        assert "Dustback Helamite" in asked.content.decode()

        removed = client.post(f"/n26/authoring/built-ins/{member.pk}/remove/")
        assert removed.status_code == 302
        assert removed["Location"] == self.address(beast)
        assert not beast.built_in_members.exists()
        # Only the membership went.
        claws.refresh_from_db()

    def test_a_beast_that_is_also_a_model_still_gets_its_own_set(
        self, beast, claws, client, person_type, gang_type
    ):
        """An exotic beast is two rows: the wargear a gang buys, and the
        model that arrives when it does. Both are called the same thing,
        and a set of built-ins may be named only once in a pack — so the
        second one to be given anything has to be named around the
        first, rather than refusing the click."""
        from n26.library.authoring import add_built_in, create_profile, create_subtype

        twin = create_profile("Dustback Helamite", person_type, gang_type, price=45)
        add_built_in(twin, create_subtype("Exotic Beast"))

        added = client.post(
            self.address(beast),
            {"act": "built_in", "thing_kind": "weapon", "thing_weapon": str(claws.pk)},
        )

        assert added.status_code == 302
        beast.refresh_from_db()
        assert [str(row.assignable) for row in beast.built_in_members] == [
            "Helamite claws"
        ]
        # Two sets, each named for the thing that holds it.
        assert beast.built_ins.name == "Dustback Helamite (wargear) built-ins"
        assert twin.built_ins.name == "Dustback Helamite built-ins"

    def test_a_weapon_keeps_its_profiles_and_gains_the_section(self, claws, client):
        """The first page to carry two sections of parts. A weapon's
        profiles are its own; coming with something is everyone's,
        and the two must not stand in for each other."""
        body = client.get(f"/n26/authoring/weapon/{claws.pk}/").content.decode()

        assert "Weapon profiles" in body
        assert "Comes with" in body
        assert 'value="built_in"' in body

    def test_the_built_ins_form_says_which_it_is(self, claws, client):
        """Several forms post to a weapon's address, so each has to say
        which it is. A post naming nothing is nobody's form: the lines a
        weapon fires are added at an address of their own, and nothing
        else here answers to silence."""
        from n26.library.authoring import create_wargear

        pouch = create_wargear("Ammo pouch", price=10)
        added = client.post(
            f"/n26/authoring/weapon/{claws.pk}/",
            {
                "act": "built_in",
                "thing_kind": "wargear",
                "thing_wargear": str(pouch.pk),
            },
        )

        assert added.status_code == 302
        claws.refresh_from_db()
        assert claws.built_in_members.count() == 1

        nobody = client.post(
            f"/n26/authoring/weapon/{claws.pk}/",
            {"name": "Warp round", "price": "10"},
        )

        assert nobody.status_code == 200  # redrawn, nothing added
        assert not claws.profiles.filter(name="Warp round").exists()
        assert claws.built_in_members.count() == 1


class TestEveryCarrierIsOfferedTheSection:
    """Discovering guard: which pages offer built-ins is read off the
    model, never listed, so a new assignable kind gets the section
    without anyone remembering to add it.

    A carrier is a kind that can come with things *and* says a set on it
    would ever be handed over (``takes_built_ins``): the kinds that only
    arrive by being chosen say no, and offering them the section would
    author items nothing ever grants.

    The one gap among the carriers is a kind whose page is a shape of its
    own, which draws none of the shared sections. That gap is named here
    so a second bespoke page is a decision somebody makes rather than a
    section that quietly stops being offered.
    """

    @staticmethod
    def carriers():
        from n26.library.views import _model_for

        found = set()
        for kind, verb in LEAF_KINDS.items():
            model = _model_for(specs()[verb])
            if hasattr(model, "built_in_members") and model.takes_built_ins:
                found.add(kind)
        return found

    def test_there_is_something_to_check(self):
        assert len(self.carriers()) > 10

    def test_the_foundation_shapes_are_not_among_them(self):
        """A characteristic and a section are not things a fighter is
        given, so nothing about them comes with anything."""
        assert not self.carriers() & {"stat", "statline-type", "section", "category"}

    def test_every_carrier_is_offered_it(self):
        from n26.library.views import BUILT_INS_PART, _part_sections

        without = sorted(
            kind
            for kind in self.carriers()
            if BUILT_INS_PART not in _part_sections(kind)
        )
        assert not without, (
            "These kinds can come with things at model level but their pages "
            f"do not offer it: {without}. Which pages draw the section is "
            "derived from the model — do not narrow the derivation to make "
            "this pass."
        )

    def test_the_only_carrier_with_a_page_of_its_own_shape_is_the_collection(self):
        """A bespoke page draws none of the shared sections, so it is
        the one way a carrier can be offered the section in principle
        and never see it."""
        from n26.library.views import DETAIL_VIEWS

        bespoke = sorted(self.carriers() & set(DETAIL_VIEWS))
        assert bespoke == ["collection"], (
            f"{bespoke} have pages of their own shape, which draw no built-ins "
            "section. A collection is a list of what may be bought, so coming "
            "with something is not a question it answers; decide the same for "
            "any new one rather than leaving it out by accident."
        )


class TestAGangTypeThatCannotBeFounded:
    """The switch that keeps a gang type off the create-a-gang screen.

    An author needs to see it and change it on the type's own page — a flag
    only the database knows about is not something anyone can configure.
    """

    def test_the_create_page_draws_the_switch_already_on(
        self, author, client, default_pack
    ):
        """A new type is foundable unless someone says otherwise, so the
        control has to open on. A switch drawn off would make every type
        authored here unpickable while looking like it had said nothing."""
        body = client.get("/n26/authoring/gang-type/new/").content.decode()

        assert 'name="foundable"' in body
        assert form_switch(body, "foundable")["checked"] is True

    def test_a_type_made_with_the_switch_off_cannot_be_founded(
        self, author, client, default_pack
    ):
        from n26.library.models import GangType

        client.post("/n26/authoring/gang-type/new/", {"name": "Brutes"})
        assert GangType.objects.get(name="Brutes").foundable is False

    def test_a_type_made_with_it_on_can_be(self, author, client, default_pack):
        from n26.library.models import GangType

        client.post(
            "/n26/authoring/gang-type/new/", {"name": "Escher", "foundable": "on"}
        )
        assert GangType.objects.get(name="Escher").foundable is True

    def test_the_page_opens_the_switch_on_the_value_it_has(
        self, author, client, default_pack
    ):
        """Counted as a difference between two pages, because a detail page
        carries switches of its own and only this one changes between them."""
        from n26.library.authoring import create_gang_type

        on = create_gang_type("Escher")
        off = create_gang_type("Brutes", foundable=False)

        def switches_on(row):
            body = client.get(f"/n26/authoring/gang-type/{row.pk}/").content.decode()
            return sum(props["checked"] for props in form_switches(body))

        assert switches_on(on) == switches_on(off) + 1

    def test_turning_it_off_on_the_page_sticks(self, author, client, default_pack):
        from n26.library.authoring import create_gang_type

        gang_type = create_gang_type("Brutes")
        response = client.post(
            f"/n26/authoring/gang-type/{gang_type.pk}/",
            {"act": "edit", "edit-name": "Brutes"},
        )

        assert response.status_code == 302
        gang_type.refresh_from_db()
        assert gang_type.foundable is False

    def test_the_listing_says_which_ones_are_off(self, author, client, default_pack):
        from n26.library.authoring import create_gang_type

        create_gang_type("Escher")
        open_only = client.get("/n26/authoring/gang-type/").content.decode()
        create_gang_type("Brutes", foundable=False)
        with_one_off = client.get("/n26/authoring/gang-type/").content.decode()

        assert "cannot be founded" not in open_only
        assert "cannot be founded" in with_one_off


class TestComposingOnAPageOfItsOwn:
    """Choosing the two kinds on a carrier's page leads to the composer's
    own address rather than redrawing the carrier.

    A carrier's page is long. Redrawing it on every choice of kind puts
    the reader back at its top, to scroll down and find the form again —
    and the kinds get chosen more than once while an author works out
    what they want.
    """

    NO_CONDITIONS = {
        "conditions-TOTAL_FORMS": "0",
        "conditions-INITIAL_FORMS": "0",
        "conditions-MIN_NUM_FORMS": "0",
        "conditions-MAX_NUM_FORMS": "1000",
    }

    @pytest.fixture
    def rule(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Berserker")

    def composed(self, rule, **extra):
        """A full compose submission naming this rule as the carrier."""
        return {
            "act": "compose",
            "for_kind": "rule",
            "for": str(rule.pk),
            "scope_kind": "targets_model",
            "effect_kind": "ef_adds",
            "what-thing_kind": "subtype",
            **self.NO_CONDITIONS,
            **extra,
        }

    def test_continue_leads_away_from_the_carriers_page(
        self, rule, client, default_pack
    ):
        """The step-one form points at the composer and names the carrier
        in inputs the browser turns into a query string."""
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()

        assert 'action="/n26/authoring/modifiers/new/"' in body
        assert 'name="for_kind" value="rule"' in body
        assert f'name="for" value="{rule.pk}"' in body

    def test_the_composer_page_opens_on_the_carrier_and_the_kinds(
        self, rule, client, default_pack
    ):
        """A real address: everything the page needs is in it, so it
        survives a refresh and can be linked to."""
        body = client.get(
            "/n26/authoring/modifiers/new/"
            f"?for_kind=rule&for={rule.pk}"
            "&scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        assert "New modifier for Berserker" in body
        assert 'name="what-thing_kind"' in body

    def test_what_is_composed_there_hangs_on_the_carrier(
        self, rule, client, default_pack
    ):
        """The trip must not lose which thing this is being made for."""
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        response = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            self.composed(rule, **{"what-thing_subtype": str(mounted.pk)}),
        )

        assert response.status_code == 302
        assert response.url == f"/n26/authoring/rule/{rule.pk}/"
        (made,) = rule.modifiers.all()
        assert made.effect.subtype == mounted

    def test_it_is_named_for_the_carrier_unless_told_otherwise(
        self, rule, client, default_pack
    ):
        """attach_to decides the written name, and it has to survive the
        trip or everything composed this way comes out named as though it
        were reusable."""
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            self.composed(rule, **{"what-thing_subtype": str(mounted.pk)}),
        )

        (made,) = rule.modifiers.all()
        assert made.name == "Berserker: adds Mounted"

    def test_the_reusable_switch_is_offered_once_there_is_a_carrier(
        self, rule, client, default_pack
    ):
        """With something to name the modifier after, the choice between
        that name and a generic one is a real one."""
        with_carrier = client.get(
            "/n26/authoring/modifiers/new/"
            f"?for_kind=rule&for={rule.pk}"
            "&scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()
        alone = client.get(
            "/n26/authoring/modifiers/new/?scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        props = island_props(with_carrier, "modifier-naming")
        assert props["carrier"] == "Berserker"
        assert props["name"] == {
            "htmlName": "name",
            "label": "Name",
            "helpText": "Blank writes the modifier's own sentence as its name.",
            "value": "",
            "errors": [],
        }
        assert props["reusable"]["htmlName"] == "make_reusable"
        assert props["reusable"]["label"] == "Make reusable"
        assert props["reusable"]["value"] is False
        assert "Make reusable" not in alone
        assert "modifier-naming-" not in alone

    def test_a_refused_name_returns_to_the_island_with_its_error(
        self, rule, client, default_pack
    ):
        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_model,
        )

        mounted = create_subtype("Mounted")
        modifier("Already used", targets_model(), ef_adds(mounted))
        response = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            self.composed(
                rule,
                **{
                    "what-thing_subtype": str(mounted.pk),
                    "name": "Already used",
                    "make_reusable": "on",
                },
            ),
        )

        assert response.status_code == 200
        props = island_props(response.content.decode(), "modifier-naming")
        assert props["name"]["value"] == "Already used"
        assert props["name"]["errors"] == [
            "A modifier with that name already exists in this pack."
        ]
        assert props["reusable"]["value"] is True

    def test_the_switch_still_decides_the_name(self, rule, client, default_pack):
        from n26.library.authoring import create_subtype

        mounted = create_subtype("Mounted")
        client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            self.composed(
                rule,
                **{"what-thing_subtype": str(mounted.pk), "make_reusable": "on"},
            ),
        )

        (made,) = rule.modifiers.all()
        # Named for what it does and nothing else — but still hanging on
        # the carrier the author was standing on.
        assert made.name == "the model: adds Mounted"

    def test_the_way_out_leads_back_to_the_carrier(self, rule, client, default_pack):
        """A reader who came from a rule wants to land back on that rule."""
        body = client.get(
            "/n26/authoring/modifiers/new/"
            f"?for_kind=rule&for={rule.pk}"
            "&scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        assert f'href="/n26/authoring/rule/{rule.pk}/"' in body

    def test_adding_a_condition_keeps_the_carrier(self, rule, client, default_pack):
        """The link bumps a count in the URL, and the URL is also where
        the carrier lives — a link rebuilt from the kinds alone would
        quietly turn this back into the standalone page."""
        body = client.get(
            "/n26/authoring/modifiers/new/"
            f"?for_kind=rule&for={rule.pk}"
            "&scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        added = re.search(r'href="(\?[^"]*chips=1[^"]*)"', body)
        assert added, "no add-a-condition link on the page"
        assert "for_kind=rule" in added.group(1)
        assert f"for={rule.pk}" in added.group(1)

    def test_reached_with_no_carrier_it_is_the_page_it_always_was(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier

        mounted = create_subtype("Mounted")
        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.NO_CONDITIONS,
            },
        )

        assert response.status_code == 302
        made = Modifier.objects.get(name="the model: adds Mounted")
        assert response.url == f"/n26/authoring/modifiers/{made.pk}/"

    def test_a_kind_that_carries_nothing_is_ignored(self, author, client, default_pack):
        """A made-up kind is not a way to reach an arbitrary row."""
        body = client.get(
            "/n26/authoring/modifiers/new/?for_kind=nonsense&for=1"
        ).content.decode()

        assert "New modifier" in body
        assert "New modifier for" not in body


class TestRemovingAConditionRemovesIt:
    """The Remove button under a condition takes that chip off the form
    there and then, and off the address the page is at.

    A tickbox that only takes effect on the next save reads as a control
    that does nothing. What the click must not do is lose the rest: an
    author part-way through two conditions and both panes clicks it, and
    everything except that chip has to come back.

    The chip count is read off the address, so a click that only redrew
    the page would leave the address claiming a chip the page no longer
    shows — and a reload would put it back. Every one of these follows
    the redirect and reads the page the address gives.
    """

    @pytest.fixture
    def rule(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Berserker")

    @staticmethod
    def chips(count):
        return {
            "conditions-TOTAL_FORMS": str(count),
            "conditions-INITIAL_FORMS": "0",
            "conditions-MIN_NUM_FORMS": "0",
            "conditions-MAX_NUM_FORMS": "1000",
        }

    def test_the_form_offers_a_remove_per_chip_and_no_delete_field(
        self, rule, client, default_pack
    ):
        body = client.get(
            "/n26/authoring/modifiers/new/"
            f"?for_kind=rule&for={rule.pk}"
            "&scope_kind=targets_model&effect_kind=ef_adds&chips=2"
        ).content.decode()

        assert body.count('name="drop_condition"') == 2
        assert "DELETE" not in body

    def test_the_chip_goes_and_everything_else_keeps_what_was_typed(
        self, rule, client, default_pack
    ):
        """The point of a submit rather than a link: a bare GET arrives
        carrying none of this."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        leader = create_subtype("Leader")
        mounted = create_subtype("Mounted")

        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                "name": "Half typed",
                **self.chips(2),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "conditions-1-kind": "has_subtypes",
                "conditions-1-subtypes": [str(leader.pk)],
                "drop_condition": "1",
            },
        )

        assert removed.status_code == 302
        body = client.get(removed.url).content.decode()

        assert body.count('name="drop_condition"') == 1
        assert drawn_picked(body, champion.pk)
        assert not drawn_picked(body, leader.pk)
        # The panes and the name box are not chips, and must survive too.
        assert drawn_picked(body, mounted.pk)
        assert island_props(body, "modifier-naming")["name"]["value"] == "Half typed"

    def test_the_removed_chip_stays_gone_when_the_page_is_reloaded(
        self, rule, client, default_pack
    ):
        """The whole point of the address doing the carrying. Asking for
        the same address twice must give the same page both times — the
        removed chip gone, the surviving one still holding what was
        typed into it."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        leader = create_subtype("Leader")
        mounted = create_subtype("Mounted")

        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(2),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "conditions-1-kind": "has_subtypes",
                "conditions-1-subtypes": [str(leader.pk)],
                "drop_condition": "1",
            },
        )

        assert removed.status_code == 302
        # The count the page draws from says one chip, not the two the
        # click arrived with.
        assert "conditions-TOTAL_FORMS=1" in removed.url
        # Reloading is asking for that same address a second time.
        for _ in range(2):
            body = client.get(removed.url).content.decode()
            assert body.count('name="drop_condition"') == 1
            assert drawn_picked(body, champion.pk)
            assert not drawn_picked(body, leader.pk)

    def test_the_carrier_survives_the_click(self, rule, client, default_pack):
        """The address says which thing is being composed for, and the
        click rewrites that address — a rewrite that dropped the carrier
        would quietly turn this into the standalone page."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")

        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "drop_condition": "0",
            },
        )

        assert f"for={rule.pk}" in removed.url
        assert f"New modifier for {rule}" in client.get(removed.url).content.decode()

    def test_adding_a_condition_after_a_removal_keeps_what_was_typed(
        self, rule, client, default_pack
    ):
        """Add is a link built from the address, and after a removal the
        address is where the form lives. A link that named a chip count
        of its own would send the author back to an empty form."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        leader = create_subtype("Leader")

        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                **self.chips(2),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "conditions-1-kind": "has_subtypes",
                "conditions-1-subtypes": [str(leader.pk)],
                "drop_condition": "1",
            },
        )
        body = client.get(removed.url).content.decode()
        added = re.search(r'href="(\?[^"]*conditions-TOTAL_FORMS=2[^"]*)"', body)
        assert added, "no add-a-condition link offering a second chip"

        grown = client.get(
            "/n26/authoring/modifiers/new/" + unescape(added.group(1))
        ).content.decode()
        assert grown.count('name="drop_condition"') == 2
        assert drawn_picked(grown, champion.pk)

    def test_removing_the_first_renumbers_rather_than_leaving_a_gap(
        self, rule, client, default_pack
    ):
        """A formset addresses its forms by position. Left as a gap, the
        missing position reads as an emptied chip and the last one is
        read twice."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        leader = create_subtype("Leader")
        mounted = create_subtype("Mounted")

        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(2),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "conditions-1-kind": "has_subtypes",
                "conditions-1-subtypes": [str(leader.pk)],
                "drop_condition": "0",
            },
        )
        body = client.get(removed.url).content.decode()

        assert body.count('name="drop_condition"') == 1
        assert drawn_picked(body, leader.pk)
        assert not drawn_picked(body, champion.pk)
        assert 'name="conditions-0-subtypes"' in body
        assert 'name="conditions-1-subtypes"' not in body

    def test_the_click_saves_nothing(self, rule, client, default_pack):
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        mounted = create_subtype("Mounted")

        response = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "drop_condition": "0",
            },
        )

        assert response.status_code == 302
        assert rule.modifiers.count() == 0

    def test_a_half_filled_form_is_not_refused_yet(self, rule, client, default_pack):
        """Taking a condition off is an edit to the form. A pane the
        author has not reached is not a refusal, and lighting the whole
        form up red for clicking Remove would read as one."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                # what-thing is deliberately left unanswered.
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "drop_condition": "0",
            },
        )
        body = client.get(removed.url).content.decode()

        assert "This field is required" not in body
        assert "cannot apply" not in body

    def test_a_form_too_long_to_write_into_an_address_is_redrawn_instead(
        self, rule, client, default_pack, monkeypatch
    ):
        """A condition may name any number of weapons, and enough of
        them make an address longer than a server will accept. The chip
        still goes and nothing typed is lost — only the address stays
        where it was, so this one page comes back on a reload."""
        from n26.library import views
        from n26.library.authoring import create_subtype

        monkeypatch.setattr(views, "MAX_CARRIED_ADDRESS", 40)
        champion = create_subtype("Champion")
        leader = create_subtype("Leader")

        response = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "name": "Half typed",
                **self.chips(2),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "conditions-1-kind": "has_subtypes",
                "conditions-1-subtypes": [str(leader.pk)],
                "drop_condition": "1",
            },
        )

        assert response.status_code == 200
        body = response.content.decode()
        assert body.count('name="drop_condition"') == 1
        assert drawn_picked(body, champion.pk)
        assert not drawn_picked(body, leader.pk)
        assert island_props(body, "modifier-naming")["name"]["value"] == "Half typed"

    def test_a_position_naming_no_chip_leaves_the_form_alone(
        self, rule, client, default_pack
    ):
        """The number comes off the page, so it is not to be trusted."""
        from n26.library.authoring import create_subtype

        champion = create_subtype("Champion")
        removed = client.post(
            f"/n26/authoring/modifiers/new/?for_kind=rule&for={rule.pk}",
            {
                "act": "compose",
                "for_kind": "rule",
                "for": str(rule.pk),
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                **self.chips(1),
                "conditions-0-kind": "has_subtypes",
                "conditions-0-subtypes": [str(champion.pk)],
                "drop_condition": "7",
            },
        )
        body = client.get(removed.url).content.decode()

        assert drawn_picked(body, champion.pk)
        assert body.count('name="drop_condition"') == 1


class TestThePickersStillPostWhatTheySay:
    """A picker is drawn inside <c-n26.filter-select>, which puts a filter
    box over a long list. What the browser sends must not move: the same
    control name, and the row's own primary key rather than the words on
    the option.

    Worth its own suite because the failure it guards against is quiet. A
    picker that posted its label would raise nothing and save nothing —
    the form would come back saying the field was required, or worse find
    a different row that happens to print the same name.
    """

    NO_CONDITIONS = {
        "conditions-TOTAL_FORMS": "0",
        "conditions-INITIAL_FORMS": "0",
        "conditions-MIN_NUM_FORMS": "0",
        "conditions-MAX_NUM_FORMS": "1000",
    }

    @pytest.fixture
    def rule(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        return create_rule("Berserker")

    def test_the_composer_offers_a_real_select_carrying_primary_keys(
        self, rule, client, default_pack
    ):
        """What an author picks is the row's id, not the words beside it."""
        from n26.library.authoring import create_skill

        nerves = create_skill("Nerves of Steel")
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        assert 'name="what-thing_skill"' in body
        assert f'value="{nerves.pk}"' in body
        assert "Nerves of Steel" in body

    def test_the_union_markers_survive_the_wrapper(self, rule, client, default_pack):
        """The page's own script finds the member controls by these
        attributes and hides all but the chosen kind's. A wrapper that
        swallowed them would leave every picker on the screen at once."""
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        assert 'data-union-kind="thing"' in body
        assert 'data-union-of="thing"' in body
        assert 'data-union-member="skill"' in body

    def test_a_long_picker_gives_react_the_native_select_contract(
        self, rule, client, default_pack
    ):
        from n26.library.authoring import create_skill

        skills = [create_skill(f"Filter skill {index:02}") for index in range(16)]
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_adds"
        ).content.decode()

        props = island_props(body, "filter-select", name="what-thing_skill")
        assert props["attrs"] == {
            "data-union-of": "thing",
            "data-union-member": "skill",
        }
        assert {option["value"] for option in props["options"]} >= {
            str(skill.pk) for skill in skills
        }

    def test_picking_through_the_composer_writes_that_row(
        self, rule, client, default_pack
    ):
        """The contract end to end: post the name and the value the page
        offered, and the modifier names the row that was picked."""
        from n26.library.authoring import create_skill

        create_skill("Nerves of Steel")
        wanted = create_skill("Spring Up")

        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "skill",
                "what-thing_skill": str(wanted.pk),
                **self.NO_CONDITIONS,
            },
        )

        assert response.status_code == 302
        (made,) = rule.modifiers.all()
        assert made.effect.skill == wanted

    def test_two_rows_printing_the_same_name_stay_apart(
        self, rule, client, default_pack
    ):
        """Two houses' beasts carry jaws of the same name. The picker
        labels them apart and posts an id, so choosing the second cannot
        land on the first."""
        from n26.library.authoring import create_skill

        first = create_skill("Ferocious jaws", qualifier="Delaque")
        second = create_skill("Ferocious jaws", qualifier="Goliath")

        client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "skill",
                "what-thing_skill": str(second.pk),
                **self.NO_CONDITIONS,
            },
        )

        (made,) = rule.modifiers.all()
        assert made.effect.skill == second
        assert made.effect.skill != first

    def make_autogun(self, client, weapon_statline_type):
        from n26.library.models import Weapon

        client.post(
            "/n26/authoring/weapon/new/",
            {
                "name": "Autogun",
                "slots": "1",
                "statline_type": str(weapon_statline_type.pk),
                "price": "20",
                "trade_point_price": "0",
            },
        )
        return Weapon.objects.get(name="Autogun")

    def test_a_many_picker_still_posts_every_value_chosen(
        self, author, client, default_pack, weapon_statline_type
    ):
        """The multi-select is wrapped too, and a browser posts one value
        per chosen option however the list was narrowed to find them."""
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")
        unwieldy = create_trait("Unwieldy")
        create_trait("Web")

        response = client.post(
            f"/n26/authoring/weapons/{autogun.pk}/add-profile/",
            {
                "name": "Burst",
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(rapid_fire.pk), str(unwieldy.pk)],
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
        )

        assert response.status_code == 302
        profile = WeaponProfile.objects.get(weapon=autogun, name="Burst")
        assert set(profile.traits.all()) == {rapid_fire, unwieldy}

    def test_the_many_picker_is_still_a_native_multiple_select(
        self, author, client, default_pack, weapon_statline_type
    ):
        """Whatever the filter box draws over it, underneath is the control
        a browser knows how to submit with no script at all."""
        from n26.library.authoring import create_trait

        autogun = self.make_autogun(client, weapon_statline_type)
        rending = create_trait("Rending")

        body = client.get(
            f"/n26/authoring/weapons/{autogun.pk}/add-profile/"
        ).content.decode()
        picker = re.search(r'<select[^>]*name="traits".*?</select>', body, re.S)
        assert picker, "the traits picker is not a <select>"
        assert "multiple" in picker.group(0)
        assert "n26-select-multiple" in picker.group(0)
        assert f'value="{rending.pk}"' in picker.group(0)


class TestAShortManyPickerShowsWhatIsChosen:
    """Profile types is two options. Below min_options the filter box
    leaves the native select in view, so the chosen row has to look
    chosen."""

    def test_the_profile_types_list_marks_the_chosen_row(
        self, author, client, default_pack, fighter_type, vehicle_type
    ):
        body = client.get(
            "/n26/authoring/modifiers/new/"
            "?scope_kind=targets_model&effect_kind=ef_adds&chips=1"
            "&conditions-0-kind=is_profile_type"
            f"&conditions-0-profile_types={fighter_type.pk}"
        ).content.decode()
        picker = re.search(
            r'<select[^>]*name="conditions-0-profile_types".*?</select>',
            body,
            re.S,
        )
        assert picker, "the profile types picker is not a <select>"
        tag = picker.group(0)
        assert "multiple" in tag
        assert "n26-select-multiple" in tag
        assert "Fighter" in tag
        assert "Vehicle" in tag


class TestTheDocumentation:
    """The documentation section: the markdown files beside the views,
    rendered for authors, staff-only."""

    def test_the_index_names_both_pages_and_says_what_each_holds(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/docs/").content.decode()
        assert "/n26/authoring/docs/concepts/" in body
        assert "/n26/authoring/docs/recipes/" in body
        assert "Core Concepts" in body
        assert "Recipes" in body
        assert "one card per kind, with its fields and behaviour" in body

    def test_the_index_names_the_collections_page(self, author, client, default_pack):
        body = client.get("/n26/authoring/docs/").content.decode()
        assert "/n26/authoring/docs/collections/" in body
        assert "Collections" in body

    def test_an_author_reads_the_rendered_collections_page(
        self, author, client, default_pack
    ):
        """The one page that explains the kind end to end, so it has to
        reach every use a collection is put to."""
        body = client.get("/n26/authoring/docs/collections/").content.decode()
        for heading in [
            "Creating an equipment list",
            "Restricting an entry",
            "Preparing a collection for players",
            "Using a collection as a hire list",
            "Replacing the main list",
            "Sections for skills and powers",
            "The Trading Post",
        ]:
            assert heading in body, heading
        assert "## Sections" not in body
        assert re.search(r"<h1[^>]*>\s*Collections", body)

    def test_the_library_index_points_at_the_documentation(
        self, author, client, default_pack
    ):
        assert "/n26/authoring/docs/" in client.get("/n26/authoring/").content.decode()

    def test_an_author_reads_the_rendered_cookbook(self, author, client, default_pack):
        body = client.get("/n26/authoring/docs/recipes/").content.decode()
        assert "Corrupted gangs" in body
        # Rendered, not served raw: the markdown heading became a tag.
        assert "## Corrupted gangs" not in body

    def test_an_author_reads_the_rendered_concepts(self, author, client, default_pack):
        body = client.get("/n26/authoring/docs/concepts/").content.decode()
        assert "Hiring" in body
        assert "## Hiring" not in body
        # The page names itself, whatever the file calls its own title.
        assert re.search(r"<h1[^>]*>\s*Core Concepts", body)

    def test_the_file_title_yields_to_the_page_header(
        self, author, client, default_pack
    ):
        """A file opens with its own title so it reads whole as markdown;
        the page supplies that heading itself, so exactly one is drawn."""
        body = client.get("/n26/authoring/docs/recipes/").content.decode()
        headings = [
            heading.get_text(" ", strip=True)
            for heading in BeautifulSoup(body, "html.parser").find_all("h1")
        ]
        assert headings.count("Recipes") == 1

    def test_every_heading_is_an_anchor_that_links_to_itself(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/docs/recipes/").content.decode()
        assert '<h2 id="corrupted-gangs"><a href="#corrupted-gangs">' in body
        assert '<h3 id="the-choice"><a href="#the-choice">' in body

    def test_the_concepts_headings_are_anchors_too(self, author, client, default_pack):
        body = client.get("/n26/authoring/docs/concepts/").content.decode()
        assert '<h2 id="hiring"><a href="#hiring">' in body

    def test_the_contents_list_the_sections_of_the_page_being_read(
        self, author, client, default_pack
    ):
        """The sidebar is built from the same walk as the anchors, so a
        section named on it is a section the page can be scrolled to."""
        body = client.get("/n26/authoring/docs/concepts/").content.decode()
        assert 'href="#assignable-types"' in body

    def test_the_contents_nest_the_sections_under_their_recipe(
        self, author, client, default_pack
    ):
        from n26.library.views import _recipe_page

        source = "# T\n\n## First\n\n### Inside\n\n## Second\n\n### Inside\n"
        _, contents = _recipe_page(source)
        assert [entry["title"] for entry in contents] == ["First", "Second"]
        assert [child["title"] for child in contents[0]["children"]] == ["Inside"]
        # Two sections sharing a name get their own addresses.
        assert contents[1]["children"][0]["slug"] == "inside-2"

    def test_the_cookbooks_own_address_still_leads_to_it(
        self, author, client, default_pack
    ):
        """Links to the cookbook are out in the world, so its address
        moves the reader on rather than dropping them."""
        response = client.get("/n26/authoring/recipes/")
        assert response.status_code == 301
        assert response["Location"] == "/n26/authoring/docs/recipes/"

    def test_a_page_nobody_wrote_is_not_found(self, author, client, default_pack):
        assert client.get("/n26/authoring/docs/nonsense/").status_code == 404

    def test_a_plain_user_is_turned_away(self, client, default_pack):
        client.force_login(User.objects.create_user("cook"))
        for address in ("/n26/authoring/docs/", "/n26/authoring/docs/recipes/"):
            response = client.get(address)
            assert response.status_code == 302
            assert "login" in response["Location"]


class TestTheAboutColumn:
    """Every detail page explains its thing in sentences: what it does,
    how anyone comes to have it, and how much is assigned to it."""

    def test_the_column_says_what_a_rule_does_and_links_the_modifier(
        self, author, client, default_pack
    ):
        from n26.library.authoring import (
            create_rule,
            ef_adds,
            modifier,
            targets_model,
        )
        from n26.library.models import Modifier, Skill

        rule = create_rule("Immovable")
        skill = Skill.objects.create(name="Juggernaut")
        modifier("Grants Juggernaut", targets_model(), ef_adds(skill), attach_to=rule)

        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "What it does" in body
        assert "gain the Juggernaut skill" in body
        # The sentence is a link to the modifier it describes.
        made = Modifier.objects.get(name="Grants Juggernaut")
        assert f"/n26/authoring/modifiers/{made.pk}/" in body

    def test_the_column_counts_what_is_assigned(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        rule = create_rule("Unclaimed")
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "Assigned to" in body
        assert "No gang yet." in body


class TestAttachingAModifierToSeveral:
    """The listing of a kind that can carry modifiers lets an author tick
    rows and hang one modifier on all of them from a page of its own.
    The ticked rows travel in the address, so the page reloads and Back
    works; a thing that already carries the modifier is left as it is."""

    @pytest.fixture
    def gang_types(self, default_pack):
        from n26.library.authoring import create_gang_type

        return [create_gang_type(name) for name in ("Escher", "Goliath", "Orlock")]

    @pytest.fixture
    def grant(self, default_pack):
        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_every_model,
        )

        return modifier(
            "Everyone is Agile",
            targets_every_model(),
            ef_adds(create_subtype("Agile")),
        )

    def test_the_listing_offers_a_box_per_row_where_modifiers_can_hang(
        self, author, client, gang_types
    ):
        body = client.get("/n26/authoring/gang-type/").content.decode()
        props = island_props(body)
        assert {row["pk"] for row in props["rows"]} == {
            str(row.pk) for row in gang_types
        }
        assert props["bulkActionUrl"] == "/n26/authoring/gang-type/attach-modifier/"

    def test_a_kind_that_cannot_carry_modifiers_offers_none(
        self, author, client, fighter_stats
    ):
        body = client.get("/n26/authoring/stat/").content.decode()
        props = island_props(body)
        assert props["bulkActionUrl"] is None
        assert client.get("/n26/authoring/stat/attach-modifier/").status_code == 404

    def test_the_page_names_what_was_ticked_and_offers_every_modifier(
        self, author, client, gang_types, grant
    ):
        escher, goliath, _ = gang_types
        response = client.get(
            "/n26/authoring/gang-type/attach-modifier/",
            {"pk": [str(escher.pk), str(goliath.pk)]},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "Attach a modifier to 2 gang types" in body
        assert "Escher" in body
        assert "Goliath" in body
        assert "Orlock" not in body
        assert "Everyone is Agile" in body

    def test_posting_hangs_it_on_each_and_counts_those_that_had_it(
        self, author, client, gang_types, grant
    ):
        from n26.library.authoring import attach_modifiers_to

        escher, goliath, orlock = gang_types
        attach_modifiers_to(escher, [grant])

        response = client.post(
            "/n26/authoring/gang-type/attach-modifier/",
            {"pk": [str(t.pk) for t in gang_types], "modifier": str(grant.pk)},
            follow=True,
        )

        assert response.redirect_chain[-1][0] == "/n26/authoring/gang-type/"
        assert [m.message for m in response.context["messages"]] == [
            "Attached Everyone is Agile to 2 gang types. 1 already had it."
        ]
        for gang_type in gang_types:
            assert list(gang_type.modifiers.all()) == [grant]

    def test_posting_again_changes_nothing_and_says_so(
        self, author, client, gang_types, grant
    ):
        data = {"pk": [str(t.pk) for t in gang_types], "modifier": str(grant.pk)}
        client.post("/n26/authoring/gang-type/attach-modifier/", data, follow=True)
        response = client.post(
            "/n26/authoring/gang-type/attach-modifier/", data, follow=True
        )
        assert [m.message for m in response.context["messages"]] == [
            "Every selected gang type already had Everyone is Agile."
        ]
        for gang_type in gang_types:
            assert gang_type.modifiers.count() == 1

    def test_nothing_ticked_sends_the_author_back_with_a_word(
        self, author, client, gang_types, grant
    ):
        response = client.get("/n26/authoring/gang-type/attach-modifier/", follow=True)
        assert response.redirect_chain[-1][0] == "/n26/authoring/gang-type/"
        assert [m.message for m in response.context["messages"]] == [
            "Select at least one gang type first."
        ]

    def test_a_mistyped_address_is_not_an_error_page(
        self, author, client, gang_types, grant
    ):
        response = client.get(
            "/n26/authoring/gang-type/attach-modifier/", {"pk": "not-a-pk"}
        )
        assert response.status_code == 302

    def test_the_page_costs_the_same_however_many_modifiers_there_are(
        self, author, client, gang_types, grant
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import (
            create_subtype,
            ef_adds,
            modifier,
            targets_every_model,
        )

        address = "/n26/authoring/gang-type/attach-modifier/"
        data = {"pk": [str(t.pk) for t in gang_types]}
        with CaptureQueriesContext(connection) as few:
            client.get(address, data)
        for number in range(6):
            modifier(
                f"Everyone is Agile {number}",
                targets_every_model(),
                ef_adds(create_subtype(f"Agile {number}")),
            )
        with CaptureQueriesContext(connection) as more:
            client.get(address, data)
        assert len(more) <= len(few)


class TestTheInterstitialsOwnPage:
    """An interstitial is made from the menu, attached to slots from its
    own page, and detached at its own address; a slot's page names the
    interstitials it carries."""

    def slot(self):
        from n26.library.models import Slot

        return Slot.objects.get(name="House legacy")

    def test_it_is_offered_under_slots_and_pickables(self, author, client, legacy):
        body = client.get("/n26/authoring/").content.decode()
        # From the table down: the bar above it names every kind too.
        table = body[body.index('scope="colgroup"') :]

        assert "/n26/authoring/interstitial/" in table
        assert table.index("Slots &amp; Pickables") < table.index(
            "/n26/authoring/interstitial/"
        )

    def test_it_is_made_from_the_menu(self, author, client, legacy):
        from n26.library.models import Interstitial

        response = client.post(
            "/n26/authoring/interstitial/new/",
            {
                "name": "Outcast archetype",
                "title": "Choose an archetype",
                "description": "The archetype shapes the whole gang.",
                "skippable": "",
                "position": "0",
            },
        )

        assert response.status_code == 302
        made = Interstitial.objects.get(name="Outcast archetype")
        assert made.heading == "Choose an archetype"
        assert made.skippable is False
        assert made.description == "The archetype shapes the whole gang."

    def test_a_second_of_one_name_is_refused_in_words(self, author, client, legacy):
        from n26.library.authoring import create_interstitial
        from n26.library.models import Interstitial

        create_interstitial("Outcast archetype")
        body = client.post(
            "/n26/authoring/interstitial/new/",
            {
                "name": "outcast archetype",
                "title": "",
                "description": "",
                "position": "0",
            },
        ).content.decode()

        assert "An interstitial named" in body
        assert "A interstitial" not in body
        assert Interstitial.objects.count() == 1

    def test_a_slot_is_attached_from_its_own_page(self, author, client, legacy):
        from n26.library.authoring import create_interstitial

        shown = create_interstitial("Outcast archetype")
        page = f"/n26/authoring/interstitial/{shown.pk}/"
        body = client.get(page).content.decode()
        assert "Attach a slot" in body
        assert "No slots yet" in body

        response = client.post(page, {"slot": str(self.slot().pk), "position": "0"})

        assert response.status_code == 302
        assert [attachment.slot for attachment in shown.attachments.all()] == [
            self.slot()
        ]
        body = client.get(page).content.decode()
        assert "House legacy" in body
        assert f'href="/n26/authoring/slot/{self.slot().pk}/"' in body

    def test_attaching_the_same_slot_twice_is_refused_in_words(
        self, author, client, legacy
    ):
        from n26.library.authoring import create_interstitial

        shown = create_interstitial("Outcast archetype", slots=[self.slot()])
        body = client.post(
            f"/n26/authoring/interstitial/{shown.pk}/",
            {"slot": str(self.slot().pk), "position": "1"},
        ).content.decode()

        assert "already attached to House legacy" in body
        assert shown.attachments.count() == 1

    def test_a_slot_is_detached_at_its_own_address(self, author, client, legacy):
        from n26.library.authoring import create_interstitial
        from n26.library.models import Interstitial, InterstitialSlot, Slot

        shown = create_interstitial("Outcast archetype", slots=[self.slot()])
        attachment = InterstitialSlot.objects.get()
        page = f"/n26/authoring/interstitial/{shown.pk}/"
        assert (
            f'href="/n26/authoring/interstitial-attachments/{attachment.pk}/remove/"'
            in client.get(page).content.decode()
        )

        asked = client.get(
            f"/n26/authoring/interstitial-attachments/{attachment.pk}/remove/"
        ).content.decode()
        assert "Stop showing Outcast archetype when House legacy arrives?" in asked

        response = client.post(
            f"/n26/authoring/interstitial-attachments/{attachment.pk}/remove/"
        )

        assert response.status_code == 302
        assert not InterstitialSlot.objects.exists()
        # Only the attachment went: the slot and the interstitial stand.
        assert Slot.objects.filter(name="House legacy").exists()
        assert Interstitial.objects.filter(pk=shown.pk).exists()

    def test_a_slots_page_names_the_interstitials_it_carries(
        self, author, client, legacy
    ):
        from n26.library.authoring import create_interstitial

        shown = create_interstitial("Outcast archetype", slots=[self.slot()])
        body = client.get(f"/n26/authoring/slot/{self.slot().pk}/").content.decode()

        assert "Shown when this slot arrives" in body
        assert f'href="/n26/authoring/interstitial/{shown.pk}/"' in body
        assert "Outcast archetype" in body
        assert "cannot be skipped" in body

    def test_a_slot_carrying_none_says_so(self, author, client, legacy):
        body = client.get(f"/n26/authoring/slot/{self.slot().pk}/").content.decode()

        assert "No interstitial is attached to this slot yet" in body

    def test_the_listing_says_how_many_slots_show_each_one(
        self, author, client, legacy
    ):
        from n26.library.authoring import create_interstitial

        create_interstitial("Outcast archetype", slots=[self.slot()], skippable=True)
        create_interstitial("Unattached")
        body = client.get("/n26/authoring/interstitial/").content.decode()

        notes = [row["notes"] for row in island_rows(body)]
        assert ["skippable", "on 1 slot"] in notes
        assert ["cannot be skipped", "on no slot yet"] in notes

    def test_the_listing_does_not_count_an_archived_attachment(
        self, author, client, legacy
    ):
        """The slot's page and the listing agree: an archived attachment
        shows the screen nowhere."""
        from n26.library.authoring import create_interstitial, revise
        from n26.library.models import InterstitialSlot

        create_interstitial("Outcast archetype", slots=[self.slot()])
        revise(InterstitialSlot.objects.get(), archived=True)
        body = client.get("/n26/authoring/interstitial/").content.decode()

        assert "on no slot yet" in body
        assert "on 1 slot" not in body

    def test_a_slot_attached_from_a_packs_own_interstitial_joins_that_pack(
        self, author, client, legacy, homebrew
    ):
        """The attachment is a part of the interstitial, so it lands in
        the interstitial's pack — the form judges what it may reference
        by that pack, and an attachment made in a pack of its own is
        not turned away as crossing into the default one."""
        from n26.library.authoring import create_interstitial
        from n26.library.models import InterstitialSlot

        shown = create_interstitial("Outcast archetype", pack=homebrew)
        response = client.post(
            f"/n26/authoring/interstitial/{shown.pk}/",
            {"slot": str(self.slot().pk), "position": "0"},
        )

        assert response.status_code == 302
        assert InterstitialSlot.objects.get().pack == homebrew

    def test_the_listing_does_not_count_an_attachment_in_an_archived_pack(
        self, author, client, legacy, homebrew
    ):
        from n26.library.authoring import (
            attach_interstitial,
            create_interstitial,
            revise,
        )

        shown = create_interstitial("Outcast archetype")
        attach_interstitial(shown, self.slot(), pack=homebrew)
        revise(homebrew, archived=True)
        body = client.get("/n26/authoring/interstitial/").content.decode()

        assert "on no slot yet" in body
        assert "on 1 slot" not in body
        assert list(self.slot().interstitials()) == []

    def test_the_listing_says_an_archived_interstitial_is_shown_nowhere(
        self, author, client, legacy, homebrew
    ):
        """The listing draws archived rows too, and an archived screen —
        or one in an archived pack — is shown nowhere whatever it is
        attached to."""
        from n26.library.authoring import create_interstitial, revise

        shown = create_interstitial("Outcast archetype", slots=[self.slot()])
        revise(shown, archived=True)
        create_interstitial("Packed away", slots=[self.slot()], pack=homebrew)
        revise(homebrew, archived=True)
        body = client.get("/n26/authoring/interstitial/").content.decode()

        assert "shown nowhere" in body
        assert "on 1 slot" not in body and "on no slot yet" not in body
        assert list(self.slot().interstitials()) == []

    def test_the_staged_page_reads_flat_as_staged_interstitials_grow(
        self, author, client, legacy
    ):
        """The staged-content page describes each staged interstitial the
        listing's way, so it loads the attachments the listing's way."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import create_interstitial, create_slot, stage

        def grow(indices):
            for index in indices:
                slot = create_slot(f"Slot {index}", legacy, self.slot().picklist)
                stage(create_interstitial(f"Screen {index}", slots=[slot]))

        grow(range(2))
        with CaptureQueriesContext(connection) as few:
            body = client.get("/n26/authoring/staged/").content.decode()
        assert "Screen 1" in body and "on 1 slot" in body
        grow(range(2, 8))
        with CaptureQueriesContext(connection) as more:
            assert client.get("/n26/authoring/staged/").status_code == 200
        assert len(more) <= len(few)

    def test_the_listing_reads_flat_as_the_attachments_grow(
        self, author, client, legacy
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import create_interstitial, create_slot

        def grow(indices):
            for index in indices:
                slot = create_slot(f"Slot {index}", legacy, self.slot().picklist)
                create_interstitial(f"Screen {index}", slots=[slot])

        grow(range(2))
        with CaptureQueriesContext(connection) as few:
            assert client.get("/n26/authoring/interstitial/").status_code == 200
        grow(range(2, 8))
        with CaptureQueriesContext(connection) as more:
            assert client.get("/n26/authoring/interstitial/").status_code == 200
        assert len(more) <= len(few)

    def test_it_can_be_held_back_from_players(self, author, client, legacy):
        """A screen is put in front of a player by the slot it is attached
        to, so its page offers the same hold-back switch a pickable's does."""
        from n26.library.authoring import create_interstitial
        from n26.library.models import Interstitial

        shown = create_interstitial("Outcast archetype")
        body = client.get(f"/n26/authoring/interstitial/{shown.pk}/").content.decode()

        assert 'value="stage"' in body

        client.post(f"/n26/authoring/interstitial/{shown.pk}/", {"act": "stage"})

        assert Interstitial.objects.get(pk=shown.pk).staged is True

    def test_it_is_edited_on_its_own_page(self, author, client, legacy):
        from n26.library.authoring import create_interstitial
        from n26.library.models import Interstitial

        shown = create_interstitial("Outcast archetype")
        response = client.post(
            f"/n26/authoring/interstitial/{shown.pk}/",
            {
                "act": "edit",
                "edit-name": "Outcast archetype",
                "edit-title": "Pick an archetype",
                "edit-description": "Shapes the gang.",
                "edit-skippable": "on",
                "edit-position": "2",
            },
        )

        assert response.status_code == 302
        edited = Interstitial.objects.get(pk=shown.pk)
        assert (edited.title, edited.skippable, edited.position) == (
            "Pick an archetype",
            True,
            2,
        )

    def test_the_page_is_staff_only(self, client, legacy):
        from django.contrib.auth.models import User

        from n26.library.authoring import create_interstitial

        shown = create_interstitial("Outcast archetype")
        client.force_login(User.objects.create_user("player"))

        assert client.get(f"/n26/authoring/interstitial/{shown.pk}/").status_code in (
            302,
            403,
        )
