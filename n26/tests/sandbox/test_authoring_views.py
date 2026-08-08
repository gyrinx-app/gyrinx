"""The authoring views: leaf assignables created through real pages.

The admin forms come before the preview pane, starting at the leaves.
These tests hold the pages to the same standard as the layers beneath
them:

* every leaf kind the menu offers is backed by a spec, discovered not
  trusted;
* the page's form is the spec's form — the help an author reads is the
  model's own words;
* a valid submit performs the ``create_*`` verb (the row lands in the
  default pack, exactly as ingestion should);
* refusals are words on the form — a duplicate name never becomes a
  database error;
* the surface is staff-only.
"""

import re

import pytest
from django.contrib.auth.models import User

from n26.library.specs import specs
from n26.library.views import LEAF_KINDS

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


class TestTheMenuIsBackedBySpecs:
    def test_there_is_something_to_check(self):
        assert {"subtype", "rule", "wargear", "category"} <= set(LEAF_KINDS)

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_kind_has_a_spec(self, kind):
        assert LEAF_KINDS[kind] in specs(), (
            f"The authoring menu offers {kind!r} but no spec backs "
            f"{LEAF_KINDS[kind]} — the page could not generate its form."
        )

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_kind_can_say_which_field_is_its_name(self, kind):
        """A duplicate is refused by writing the error onto the field an
        author reads as the thing's name. A spec naming a field it does
        not have would crash on that refusal instead of showing it."""
        spec = specs()[LEAF_KINDS[kind]]
        assert spec.identity in spec.fields, (
            f"The {kind} spec says its name field is {spec.identity!r}, but "
            f"its fields are {', '.join(spec.fields)}. Set identity= on the "
            f"spec to whichever of those an author reads as the name."
        )

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_kind_reads_both_ways(self, kind):
        """Editing writes a form's fields straight onto the row, using
        the same spec that describes the creating verb. That only works
        while every field names a column on the thing being made — a
        field sourced from another model, or naming nothing, would be
        silently dropped on save."""
        from n26.library.specs import Conditions, Union

        spec = specs()[LEAF_KINDS[kind]]
        model = spec.creates
        for name, kind_of_field in spec.fields.items():
            assert not isinstance(kind_of_field, (Union, Conditions)), (
                f"{kind}'s {name} is a {type(kind_of_field).__name__}, which "
                f"has no single column to write back to. Editing would drop "
                f"it — give the kind its own edit path before adding this."
            )
            source = getattr(kind_of_field, "source", None)
            assert source is not None and source[0] is model, (
                f"{kind}'s {name} is not a column on {model.__name__}, so "
                f"editing cannot write it back. Point its source at the "
                f"model the verb makes."
            )

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_page_renders(self, kind, author, client, default_pack):
        response = client.get(f"/n26/authoring/{kind}/")
        assert response.status_code == 200

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_kind_has_a_create_page(self, kind, author, client, default_pack):
        response = client.get(f"/n26/authoring/{kind}/new/")
        assert response.status_code == 200

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_no_switch_is_handed_a_value_javascript_cannot_read(
        self, kind, author, client, default_pack
    ):
        """A switch takes its opening state as a JavaScript literal. An
        untouched field's value is None, and `none` is not one — it
        throws on init, leaving a control that never reflects what it
        is bound to and posts whatever the browser left in it."""
        body = client.get(f"/n26/authoring/{kind}/new/").content.decode()
        assert "switchInput(false, none)" not in body
        assert "switchInput(false, None)" not in body

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_leaf_page_renders_with_rows_in_it(
        self, kind, author, client, default_pack
    ):
        """An empty page exercises none of the listing, which is how a
        listing that could not read a row shipped: the foundation kinds
        are not assignables and have no authoring label."""
        from n26.library.standard_content import STANDARD_CONTENT

        for item in STANDARD_CONTENT.values():
            item.create()

        response = client.get(f"/n26/authoring/{kind}/")
        assert response.status_code == 200

    def test_an_unknown_kind_is_a_404(self, author, client, default_pack):
        assert client.get("/n26/authoring/gadget/").status_code == 404


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
    """A kind's own page documents the kind and lists every one of
    them. Making one is a button to a page of its own; changing one is
    the row itself."""

    def test_it_documents_the_kind_and_offers_a_way_in(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/rule/").content.decode()

        # The model's own docstring is the documentation, as on the
        # create page — a fragment of it with nothing HTML escapes.
        assert "A named special rule on a fighter" in body
        assert "/n26/authoring/rule/new/" in body

    def test_it_carries_no_create_form(self, author, client, default_pack):
        """The form moved to its own page. Left here it would post to a
        view that no longer creates anything, and say nothing about
        why."""
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
        """The search narrows rows already on the page, so each row
        brings its own haystack — name and notes, lowercased."""
        from n26.library.authoring import create_rule

        create_rule("Lead Ritual", annotation="Leader only")
        body = client.get("/n26/authoring/rule/").content.decode()

        assert "lead ritual" in body  # the haystack, beside the printed name
        assert "Lead Ritual" in body


class TestCreatingALeaf:
    def test_the_form_shows_the_models_own_words(self, author, client, default_pack):
        from n26.library.models import Rule

        body = client.get("/n26/authoring/rule/new/").content.decode()
        assert str(Rule._meta.get_field("annotation").help_text) in body

    def test_a_valid_submit_performs_the_verb(self, author, client, default_pack):
        from n26.library.models import Subtype

        response = client.post("/n26/authoring/subtype/new/", {"name": "Mounted"})
        assert response.status_code == 302  # created, back to the page

        row = Subtype.objects.get(name="Mounted")
        assert row.pack == default_pack  # landed exactly as ingestion would

        body = client.get("/n26/authoring/subtype/").content.decode()
        assert "Mounted" in body  # the listing shows it

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

        assert response.status_code == 200  # back on the form, not a 500
        assert "already exists in this pack" in response.content.decode()
        assert Subtype.objects.filter(name="Mounted").count() == 1

    def test_a_duplicate_stat_refuses_in_words_too(self, author, client, default_pack):
        """A stat has no field called "name" — it has a short one and a
        full one — and a second Movement used to crash the page rather
        than say a Movement already existed."""
        from n26.library.models import Stat

        made = {"short_name": "M", "full_name": "Movement"}
        client.post("/n26/authoring/stat/new/", made)
        response = client.post("/n26/authoring/stat/new/", made)

        assert response.status_code == 200  # back on the form, not a 500
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
    """A thing's own page is where it is changed. The form is the same
    spec-generated one the create page uses, opened on a row that
    already exists."""

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
        assert Rule.objects.count() == 1  # changed, not copied

    def test_a_field_cleared_is_cleared(self, author, client, default_pack):
        """Blanking an optional field has to reach the row — a save that
        only wrote the fields an author touched would leave the old
        annotation printing after the bracket was deleted."""
        from n26.library.authoring import create_rule

        rule = create_rule("Lead Ritual", annotation="Leader only")
        client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {"act": "edit", "edit-name": "Lead Ritual", "edit-annotation": ""},
        )

        rule.refresh_from_db()
        assert rule.annotation == ""

    def test_a_duplicate_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_subtype

        create_subtype("Mounted")
        wyrd = create_subtype("Wyrd")
        response = client.post(
            f"/n26/authoring/subtype/{wyrd.pk}/",
            {"act": "edit", "edit-name": "Mounted"},
        )

        assert response.status_code == 200  # back on the page, not a 500
        assert "already exists in this pack" in response.content.decode()
        wyrd.refresh_from_db()
        assert wyrd.name == "Wyrd"  # and nothing was written

    def test_editing_leaves_the_parts_alone(self, author, client, default_pack):
        """A weapon's page carries its firing lines as well as its own
        fields. Saving the one must not disturb the other."""
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
        """A weapon's page draws its own fields and the fields that add
        a firing line, and the two specs name fields alike. Sharing a
        name means sharing an id, and two switches wired to one id
        answer for each other: saving a weapon's price used to mark it
        exclusive, because the *other* form's toggle was what the
        browser read.
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
        """Saving a weapon after changing only its price must not turn
        on a switch nobody touched."""
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
        """The switch is drawn by JavaScript from a state it is handed,
        so a field that is on has to say so there — not only in the
        checkbox underneath. An exclusive weapon whose page drew the
        switch off would turn itself ordinary on the next save."""
        from n26.library.authoring import create_weapon

        weapon = create_weapon("Handbow", price=15, is_exclusive=True)
        body = client.get(f"/n26/authoring/weapon/{weapon.pk}/").content.decode()

        assert "switchInput(false, true)" in body

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
    """An author works down a list of kinds rather than down one kind, so
    every page in here offers the others — from the bar, from a listing's
    own heading, and from a row's page over the other rows of its kind."""

    def test_the_bar_offers_the_other_kinds_from_a_page_that_is_not_one(
        self, author, client, default_pack
    ):
        body = client.get("/n26/authoring/foundations/").content.decode()
        assert 'aria-label="Switch kind"' in body
        assert "/n26/authoring/weapon/" in body

    def test_a_kinds_page_marks_itself(self, author, client, default_pack):
        body = client.get("/n26/authoring/category/").content.decode()
        # The row for the kind being shown says so, and the row for any
        # other kind does not.
        assert re.search(
            r'<a href="/n26/authoring/category/"[^>]*aria-current="page"', body
        )
        assert not re.search(
            r'<a href="/n26/authoring/weapon/"[^>]*aria-current="page"', body
        )

    def test_the_listing_offers_the_kinds_beside_its_heading(
        self, author, client, default_pack
    ):
        """The same list as the bar's, and named differently: two controls
        announced identically tell a reader who cannot see where they sit
        nothing about either."""
        body = client.get("/n26/authoring/category/").content.decode()
        assert 'aria-label="Switch kind"' in body
        assert 'aria-label="Switch to another kind of content"' in body

    def test_a_rows_page_offers_the_other_rows(self, author, client, default_pack):
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        other = create_rule("Sump Sense")
        body = client.get(f"/n26/authoring/rule/{here.pk}/").content.decode()

        # Named for the kind in the model's own words, which is "special
        # rule" rather than the slug in the URL.
        assert 'aria-label="Switch to another special rule"' in body
        assert f"/n26/authoring/rule/{other.pk}/" in body
        assert "sump sense" in body  # what the panel's filter matches on

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

    def test_the_sibling_list_does_not_grow_with_the_kind(
        self, author, client, default_pack
    ):
        """Capped, and the cap is on the query — a kind with hundreds of
        rows must cost a row's page what a kind with two costs it."""
        from n26.library.authoring import create_rule

        here = create_rule("Lead Ritual")
        client.get(f"/n26/authoring/rule/{here.pk}/")  # warm any lazy setup

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
        """The platform's testers gate answers before the staff check
        does: a signed-in stranger gets the invisible-beta 404. The
        tester-but-not-staff case lives in test_platform_integration."""
        client.force_login(User.objects.create_user("player"))
        response = client.get("/n26/authoring/subtype/")
        assert response.status_code == 404


class TestSectionsAndLastingEffects:
    """The taxonomy heading is a leaf object, not free text; and
    'Injury' is one kind — Lasting Effect — whose card label is the
    profile type's own term."""

    def test_the_category_form_picks_a_section(self, author, client, default_pack):
        from n26.library.forms import generate_form
        from n26.library.specs import specs

        form = generate_form(specs()["create_category"])()
        from django import forms as django_forms

        assert isinstance(form.fields["section"], django_forms.ModelChoiceField)
        assert form.fields["section"].required  # no free text, no blank

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

    def test_named_headings_are_founded_once(self, default_pack):
        """The example suites still say create_category("Skills", …) —
        the heading is found or founded, never forked."""
        from n26.library.authoring import create_category
        from n26.library.models import Section

        create_category("Skills", "Combat")
        create_category("Skills", "Savant")
        assert Section.objects.filter(name="Skills").count() == 1

    def test_the_lasting_effect_page_and_the_profile_types_term(
        self, author, client, default_pack, fighter_type, vehicle_type
    ):
        from n26.library.models import LastingEffect

        client.post("/n26/authoring/lasting-effect/new/", {"name": "Humiliated"})
        assert LastingEffect.objects.filter(name="Humiliated").exists()

        # One kind, two words: the label is the profile type's own.
        assert fighter_type.lasting_effect_term == "Injury"
        assert vehicle_type.lasting_effect_term == "Damage"


class TestAProfilesHome:
    """A profile sorts into the hire list under a category, the same way
    a piece of wargear sorts into an equipment list. The picker names
    the section too, so two sections may both hold a Champions.

    The home is optional: a profile with none gathers at the end of the
    hire list under no heading, which is what a sheet that names no
    category should produce.
    """

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
    """Every assignable carries the author's own help
    — addable on the form, never a home for the book's rules text."""

    def test_every_assignable_leaf_form_offers_help(self):
        """Discovering: an assignable kind on the menu without a help
        field on its form has lost the author's voice."""
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
    """Every authorable kind belongs to a family — how the menu groups,
    set per model class, discovered never trusted."""

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
        # From the table down: the bar above it names every kind too, in
        # its switcher, and a position read off the whole page would be
        # measuring the chrome rather than the grouping.
        body = client.get("/n26/authoring/").content.decode()
        body = body[body.index('scope="colgroup"') :]
        # One table, a group row per family, in declaration order. The
        # heading text where it lands, not the markup around it.
        positions = [
            re.search(rf'scope="colgroup".*?>\s*{label}\s*<', body, re.S).start()
            for label in ("Base", "Model", "Gear", "Gang")
        ]
        assert positions == sorted(positions)
        # A kind sits under its family.
        assert positions[2] < body.index("wargear")
        assert positions[3] < body.index("archetype")

    def test_the_family_table(self):
        """The grouping as agreed, pinned so it changes deliberately."""
        from n26.library.models import (
            Affiliation,
            Archetype,
            Category,
            Collection,
            Counter,
            GangType,
            Hidden,
            LastingEffect,
            Profile,
            Rule,
            Section,
            Skill,
            SkillTree,
            Subtype,
            Trait,
            Wargear,
            Weapon,
            WeaponProfile,
        )
        from n26.library.models.assignable import Family

        by_family = {
            Family.BASE: [Rule, Counter, Hidden, Section, Category],
            Family.MODEL: [Subtype, Skill, LastingEffect],
            Family.GEAR: [Trait, Wargear, Weapon, WeaponProfile],
            Family.GANG: [
                GangType,
                Profile,
                Archetype,
                Affiliation,
                SkillTree,
                Collection,
            ],
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
    """Hidden, specialisation, archetype, affiliation, skill tree: the
    page makes the thing, the composer arms it later. Their verbs take
    an ``effects``/``grants_skill`` shortcut the sandbox suites use;
    the form deliberately doesn't, so there is one way to build a
    modifier and it is the composer."""

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
        assert not made.modifiers.exists()  # armed by the composer, later

    def test_the_chosen_carriers(self, author, client, default_pack):
        from n26.library.models import Affiliation, Archetype

        client.post("/n26/authoring/archetype/new/", {"name": "Brawler"})
        client.post("/n26/authoring/affiliation/new/", {"name": "Clan House"})
        assert Archetype.objects.filter(name="Brawler").exists()
        assert Affiliation.objects.filter(name="Clan House").exists()

    def test_a_specialisation(self, author, client, default_pack):
        from n26.library.models import Specialisation

        client.post("/n26/authoring/specialisation/new/", {"name": "Medicate"})
        assert Specialisation.objects.filter(name="Medicate").exists()

    def test_a_skill_tree_needs_the_set_it_stands_for(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_category
        from n26.library.models import SkillTree

        agility = create_category("Skills", "Agility")
        response = client.post(
            "/n26/authoring/skill-tree/new/",
            {"name": "Agility", "category": str(agility.pk)},
        )
        assert response.status_code == 302
        assert SkillTree.objects.get(name="Agility").category == agility

        # The token is meaningless without its home, so the form insists.
        response = client.post("/n26/authoring/skill-tree/new/", {"name": "Nowhere"})
        assert response.status_code == 200
        assert "required" in response.content.decode()
        assert not SkillTree.objects.filter(name="Nowhere").exists()


class TestKindHelp:
    """Each page explains what the kind *is* — sourced from the model's
    docstring, the same never-written rule the field help follows, one
    level up. One place to write it; authors and developers read the
    same paragraphs."""

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_kind_explains_itself(self, kind):
        from n26.library.views import _model_for, kind_help

        paragraphs = kind_help(_model_for(specs()[LEAF_KINDS[kind]]))
        assert paragraphs, f"{kind} has no docstring — the page cannot say what it is"
        assert len(paragraphs[0]) > 30  # a definition, not a stub

    @pytest.mark.parametrize("kind", sorted(LEAF_KINDS), ids=str)
    def test_every_kind_summarises_itself_in_one_line(self, kind):
        """The menu shows each kind's definition beside its name, so a
        docstring whose first paragraph rambles is a menu that rambles."""
        from n26.library.views import _model_for, kind_summary

        summary = kind_summary(_model_for(specs()[LEAF_KINDS[kind]]))
        assert summary.endswith("."), f"{kind}: not a sentence"
        assert len(summary) < 120, f"{kind}: too long for a menu row"

    def test_the_menu_shows_the_definitions(self, author, client, default_pack):
        body = client.get("/n26/authoring/").content.decode()
        assert "What the Lasting Injury and Lasting Damage tables deal out." in body
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
    """The shape the rulebook's weapon tables print: SR LR Str AP L."""
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
        # Stat definitions are shared across statline types by design:
        # a weapon's Strength is the fighter's Strength.
        stat = Stat.objects.filter(full_name=full).first() or make_stat(
            short, full, **flags
        )
        StatlineTypeStat.objects.create(
            statline_type=statline_type, stat=stat, position=position
        )
    return statline_type


class TestWeapons:
    """A weapon is the first thing with parts: the gun, then its firing
    lines. Built here exactly as the book's table prints it —
    Autogun, then its warp round at +10."""

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

    def test_creating_a_weapon_lands_on_its_page(
        self, author, client, default_pack, weapon_statline_type
    ):
        response, autogun = self.make_autogun(client, weapon_statline_type)
        assert response.status_code == 302
        assert response["Location"] == f"/n26/authoring/weapon/{autogun.pk}/"
        assert autogun.price == 20
        assert autogun.statline_type == weapon_statline_type

        # A bare weapon is a legitimate mid-authoring state; the page
        # says what's missing rather than refusing to exist.
        body = client.get(response["Location"]).content.decode()
        assert "None yet" in body

    def test_the_statline_form_is_shaped_by_the_weapon(
        self, author, client, default_pack, weapon_statline_type
    ):
        _, autogun = self.make_autogun(client, weapon_statline_type)
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        # One input per stat of *this weapon's* shape, labelled as the
        # book prints it — no spec could have known these field names.
        for short, field in (
            ("SR", "short_range"),
            ("LR", "long_range"),
            ("Str", "strength"),
            ("AP", "armour_piercing"),
            ("L", "lethality"),
        ):
            assert f'name="{field}"' in body
            # The kit's label wraps its text in a whitespace-padded span —
            # assert the words where they land, not the chrome around them.
            assert re.search(rf">\s*{re.escape(short)}\s*</span>", body)
        assert 'placeholder="4&quot;"' in body  # the stat's own example

    def test_adding_the_mandatory_profile_with_its_stats_and_traits(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_trait
        from n26.library.models import WeaponProfile

        _, autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")

        response = client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "name": "Standard",
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(rapid_fire.pk)],
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
        )
        assert response.status_code == 302

        profile = WeaponProfile.objects.get(weapon=autogun, name="Standard")
        assert profile.is_free
        assert profile.annotation == "Autogun"  # what a card prints in brackets
        assert profile.trait_names == ["Rapid Fire (1)"]
        values = {
            stat.statline_type_stat.short_name: stat.value
            for stat in profile.statline.stats.all()
        }
        # Stored as the stat says it reads: an author types 8 for a
        # range and it lands as 8", so every surface agrees without
        # each one remembering to format.
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
        """'- warp round … +10' — its own row, priced, ordered after."""
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
            client.post(
                f"/n26/authoring/weapon/{autogun.pk}/",
                {"trade_point_price": "0", **payload},
            )

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
        """The point of all of it: a fighter given this weapon shows the
        authored line on their card."""
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
        client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "name": "Standard",
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(rapid_fire.pk)],
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
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
        assert '8"' in text  # the short range, formatted by the stat


class TestWeaponAccessories:
    """An accessory is its own kind: it bolts onto a weapon rather than
    being carried, and the bracket saying what it fits — '(Las Weapons
    Only)', '(Weapons Marked With * Only)' — would be nonsense on a
    suit of armour."""

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
        """The fields that made this its own kind are gone from the one
        it used to hide in."""
        from n26.library.forms import generate_form

        form = generate_form(specs()["create_wargear"])()
        assert "fits_category" not in form.fields
        assert "fits_asterisked" not in form.fields


class TestTheQualifier:
    """Two things may print the same name — the books give Delaque's
    and Goliath's beasts the same Ferocious jaws, with different
    profiles, and both must exist. The qualifier tells them apart for
    authors and is never seen by a player."""

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
        # Both print the same, as the books do.
        assert {str(weapon) for weapon in both} == {"Ferocious jaws"}
        # And an author can still tell them apart.
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
        """A picker labelled only with what a card shows would offer the
        same row twice."""
        from n26.library.authoring import create_subtype
        from n26.library.forms import generate_form

        create_subtype("Hardened", qualifier="Goliath")
        create_subtype("Hardened", qualifier="Escher")
        form = generate_form(specs()["ef_adds"])()
        labels = [str(label) for _, label in form.fields["thing_subtype"].choices]
        assert "Hardened — Goliath" in labels
        assert "Hardened — Escher" in labels

    def test_it_is_distinguished_from_the_annotation(self):
        """Two fields beside a name with opposite visibility is a trap,
        so each says which it is."""
        from n26.library.models import Weapon

        qualifier = str(Weapon._meta.get_field("qualifier").help_text)
        annotation = str(Weapon._meta.get_field("annotation").help_text)
        assert "never by players" in qualifier
        assert "annotation instead" in qualifier
        assert "Shown in brackets after the name" in annotation


class TestAWeaponsOwnLine:
    """Most profiles have no name. The book prints the Autogun's first
    line as "Autogun" and names only what hangs beneath it — "- warp
    round" — so a blank name means "this is the weapon's line"."""

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

    def test_the_form_does_not_demand_one(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        # Requiredness is read off the verb, so this is the real check.
        from n26.library.forms import generate_form

        form = generate_form(specs()["add_weapon_profile"])()
        assert not form.fields["name"].required
        assert "Leave blank for the weapon" in body

    def test_an_unnamed_line_is_the_weapon(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.models import WeaponProfile

        autogun = self.make_autogun(client, weapon_statline_type)
        response = client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "price": "0",
                "trade_point_price": "0",
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
        )
        assert response.status_code == 302

        profile = WeaponProfile.objects.get(weapon=autogun)
        assert profile.name == ""
        assert str(profile) == "Autogun"  # not " (Autogun)"

    def test_the_page_shows_what_was_typed(
        self, author, client, default_pack, weapon_statline_type
    ):
        """The authoring page must show a profile back, or an author
        cannot check it — and an unnamed line must not read as a row
        with a missing name."""
        from n26.library.authoring import create_trait

        autogun = self.make_autogun(client, weapon_statline_type)
        rapid_fire = create_trait("Rapid Fire", "1")
        client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(rapid_fire.pk)],
                "short_range": "8",
                "long_range": "24",
                "strength": "3",
            },
        )

        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        # Labelled with the weapon and saying why — never a blank cell,
        # which would read as a name someone forgot.
        assert "<td>Autogun</td>" in body
        row = body.split("<td>Autogun</td>", 1)[1].split("</tr>", 1)[0]
        assert "own line" in row  # apostrophe is escaped in the markup
        assert "SR 8&quot;" in row  # the stats, as they will print
        assert "LR 24&quot;" in row
        assert "Str 3" in row
        assert "Rapid Fire (1)" in row
        assert "free" in row

    def test_the_page_shows_a_named_line_with_its_price(
        self, author, client, default_pack, weapon_statline_type
    ):
        autogun = self.make_autogun(client, weapon_statline_type)
        client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "name": "Warp round",
                "price": "10",
                "trade_point_price": "4",
                "short_range": "8",
            },
        )
        body = client.get(f"/n26/authoring/weapon/{autogun.pk}/").content.decode()
        # The row itself, not the field help — which also mentions the
        # weapon's own line, since that is what leaving the name blank
        # means.
        assert "<td>Warp round</td>" in body
        row = body.split("<td>Warp round</td>", 1)[1]
        assert "+10cr" in row.split("</tr>", 1)[0]
        assert "own line" not in row.split("</tr>", 1)[0]

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
        client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(rapid_fire.pk)],
                "short_range": "8",
                "long_range": "24",
            },
        )
        client.post(
            f"/n26/authoring/weapon/{autogun.pk}/",
            {
                "name": "Warp round",
                "price": "10",
                "trade_point_price": "4",
                "traits": [str(cursed.pk)],
                "short_range": "8",
                "long_range": "24",
            },
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
        # The gun's own line comes with it; paid ammo is bought.
        from n26.library.models import WeaponProfile

        buy_weapon_profile(
            held, WeaponProfile.objects.get(weapon=autogun, name="Warp round")
        )

        (card,) = render_gang(gang).models
        text = "\n".join(render_model_card(card))
        print("\n" + text)
        lines = [line.strip() for line in text.splitlines()]
        # The unnamed line *is* the weapon, so it reads on the weapon's
        # own row rather than repeating the name beneath it.
        own = next(line for line in lines if line.startswith("Autogun"))
        assert "Rapid Fire (1)" in own
        assert "30cr" in own  # the money stays
        assert not any(line.startswith("- Autogun") for line in lines)
        # The named line hangs beneath, with its own name alone — the
        # weapon in brackets belongs to a listing, not to its own card.
        named = next(line for line in lines if line.startswith("- Warp round"))
        assert named.startswith("- Warp round (+10cr)")
        assert "Cursed" in named
        assert "(Autogun)" not in named


class TestListingsSayWhatARowIs:
    """A name alone is not enough to check content by: a skill needs its
    set, a priced thing its price, and a skill tree the set it stands
    for — which is the whole of what a tree is."""

    def test_a_skill_shows_its_set_and_its_number(self, author, client, default_pack):
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["skills"].create()
        body = client.get("/n26/authoring/skill/").content.decode()
        assert "Catfall" in body
        assert "Agility" in body
        assert "rolled on a 1" in body

    def test_an_inherent_skill_shows_no_number(self, author, client, default_pack):
        """A rule grants it, so it is rolled for on no table."""
        from n26.library.standard_content import STANDARD_CONTENT

        STANDARD_CONTENT["skills"].create()
        body = client.get("/n26/authoring/skill/").content.decode()
        row = body.split("Juggernaut", 1)[1].split("</tr>", 1)[0]
        assert "Inherent" in row
        assert "rolled on" not in row

    def test_a_skill_tree_says_which_set_it_stands_for(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_category, create_skill_tree

        create_skill_tree("Agility", create_category("Skills", "Agility"))
        body = client.get("/n26/authoring/skill-tree/").content.decode()
        assert "stands for Agility" in body

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


class TestTheGangSurface:
    """The straight line to a fighter entry: a gang type, a profile on
    its list, a named equipment list, the list granted to the profile —
    and the profile's page saying what it may use. Every step through
    the pages, as an author would take it."""

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

        # A profile with nothing granted yet is a legitimate state; the
        # page says so rather than refusing to exist.
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
            {"thing_kind": "collection", "thing_collection": str(escher_list.pk)},
        )
        assert response.status_code == 302

        # The grant is a built-in: the set was founded for the profile,
        # and the member names the list.
        ganger.refresh_from_db()
        member = ganger.built_in_members.get()
        assert member.assignable == escher_list

        # The profile's page says what it may use…
        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()
        assert "Comes with" in body
        assert "House Escher Equipment List" in body
        assert "a list it may use" in body

        # …and so does its row in the listing.
        listing = client.get("/n26/authoring/profile/").content.decode()
        assert "uses House Escher Equipment List" in listing
        assert "Escher" in listing

    def test_a_counter_built_in_keeps_its_opening_value(
        self, author, client, default_pack, person_type
    ):
        """The other union arm the PoC needs working: Starting XP as a
        counter member with an amount."""
        from n26.library.authoring import create_counter

        _, ganger = self.make_ganger(client, person_type)
        xp = create_counter("XP")

        client.post(
            f"/n26/authoring/profile/{ganger.pk}/",
            {"thing_kind": "counter", "thing_counter": str(xp.pk), "amount": "6"},
        )
        ganger.refresh_from_db()
        member = ganger.built_in_members.get()
        assert member.assignable == xp
        assert member.amount == 6

        body = client.get(f"/n26/authoring/profile/{ganger.pk}/").content.decode()
        assert "opening value 6" in body

    def test_the_grant_needs_a_pick(self, author, client, default_pack, person_type):
        """A kind chosen with nothing picked refuses in words."""
        _, ganger = self.make_ganger(client, person_type)
        response = client.post(
            f"/n26/authoring/profile/{ganger.pk}/", {"thing_kind": "collection"}
        )
        assert response.status_code == 200
        assert "Pick or name a collection." in response.content.decode()
        assert not ganger.built_in_members.exists()

    def test_the_page_carries_the_union_toggle(
        self, author, client, default_pack, person_type
    ):
        """The kind select and its members are marked, and the script
        that reads the markers ships with the page — the pair that lets
        the browser show only the chosen kind's picker."""
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
        """The quick build-out: create the Ganger, its Starting XP, its
        list access and both its subtypes in a single POST, and land on
        a detail page already saying all of it."""
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


class TestTheCollectionPage:
    """A collection's page is a preview: the definition (sweeps and
    entries), and what it means right now — the same browse structure
    the player-side listing draws, so what an author sees is what a
    gang will get."""

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

    def test_the_trading_post_previews_its_membership(
        self, author, client, default_pack
    ):
        """The criteria case: the page shows the sweeps and what they
        sweep in today — TP-priced guns with their ammo nested, the
        unoffered needler nowhere."""
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
        assert "Kraken round" in body  # nested under its gun
        assert "House-pattern needler" not in body
        assert "Ranged Weapons" in body  # sectioned like the book

    def test_membership_by_criteria_updates_itself(self, author, client, default_pack):
        """Author a weapon through the pages and it is simply there —
        no entry rows, nothing to maintain."""
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
        assert "10cr here" in body  # the entry's own price, in the definition
        assert "priced by this list" in body  # and marked in the preview
        assert ">E<" in body  # the heirloom's TP cell


class TestTheModifierSection:
    """Every assignable kind's page carries its modifiers: what hangs
    here in scope-and-effect sentences, an attach picker for reusables,
    and the two-step composer — kinds first (carried in the URL, so
    step two survives a refresh), then the panes those kinds call for.
    The section is derived from the mixin's M2M, never enumerated, so
    a new assignable kind gets it without anyone remembering to say so.
    """

    #: The empty condition formset's bookkeeping, present on every
    #: compose POST the way the browser would send it.
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
        assert 'name="scope_kind"' in body  # step one is always offered

    def test_a_foundation_kind_has_a_page_without_one(
        self, author, client, default_pack
    ):
        """A stat is not an assignable, so nothing can be hung on it —
        but it is still authored, so it still has a page to be edited
        on."""
        from n26.library.authoring import create_stat

        stat = create_stat("M", "Movement", is_inches=True)
        response = client.get(f"/n26/authoring/stat/{stat.pk}/")

        assert response.status_code == 200
        body = response.content.decode()
        assert 'name="edit-full_name"' in body  # the edit form
        assert 'name="scope_kind"' not in body  # but no composer

    def test_step_two_renders_the_panes_the_kinds_call_for(
        self, rule, client, default_pack
    ):
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_changes_stat"
        ).content.decode()
        assert 'name="what-stat"' in body
        assert 'name="what-amount"' in body
        assert 'name="who-when_directly_assigned"' in body

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
        """URL-driven: chips rides the query string, so the empty chip
        survives a refresh and needs no JavaScript."""
        body = client.get(
            f"/n26/authoring/rule/{rule.pk}/"
            "?scope_kind=targets_model&effect_kind=ef_adds&chips=1"
        ).content.decode()
        assert 'name="conditions-0-kind"' in body
        assert "chips=2" in body  # the next link is already offered

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
        # Detached, not destroyed: the other carrier keeps it.
        assert list(other.modifiers.all()) == [shared]

    def test_keep_reusable_saves_without_attaching(self, rule, client, default_pack):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier

        mounted = create_subtype("Mounted")
        response = client.post(
            f"/n26/authoring/rule/{rule.pk}/",
            {
                "act": "compose",
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                "what-thing_kind": "subtype",
                "what-thing_subtype": str(mounted.pk),
                "keep_reusable": "on",
                **self.NO_CONDITIONS,
            },
        )
        assert response.status_code == 302
        assert rule.modifiers.count() == 0
        (made,) = Modifier.objects.all()
        # …and the page now offers it in the attach picker.
        body = client.get(f"/n26/authoring/rule/{rule.pk}/").content.decode()
        assert "Attach an existing modifier" in body
        assert made.name in body

    def test_the_weapon_page_keeps_its_parts_and_gains_the_section(
        self, author, client, default_pack, weapon_statline_type
    ):
        from n26.library.authoring import create_weapon

        gun = create_weapon("Autogun", statline_type=weapon_statline_type)
        body = client.get(f"/n26/authoring/weapon/{gun.pk}/").content.decode()
        assert "Add a weapon profile" in body
        assert "does nothing special until" in body


class TestTheModifiersPage:
    """The standalone page: every modifier in the pack listed with its
    sentences and carrier count, and the composer with nothing to
    attach to — what it makes is reusable by construction."""

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
        assert "Grants Mounted" in body
        assert "adds Mounted" in body
        assert "on 1 carrier" in body
        assert "reusable — attached nowhere yet" in body

    def test_composing_here_attaches_nowhere(self, author, client, default_pack):
        from n26.library.authoring import create_subtype
        from n26.library.models import Modifier

        mounted = create_subtype("Mounted")
        response = client.post(
            "/n26/authoring/modifiers/",
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
        # Reusable by construction: no carrier anywhere holds it.
        from n26.library.views import _carrier_count

        assert _carrier_count(made) == 0

    def test_the_two_step_flow_works_here_too(self, author, client, default_pack):
        body = client.get(
            "/n26/authoring/modifiers/"
            "?scope_kind=targets_weapons&effect_kind=ef_adds&chips=1"
        ).content.decode()
        assert 'name="what-thing_kind"' in body
        assert 'name="conditions-0-kind"' in body
        # No keep-reusable switch: there is nothing to attach to.
        assert 'name="keep_reusable"' not in body

    def test_a_refusal_stays_on_the_page_in_words(self, author, client, default_pack):
        from n26.library.authoring import create_trait

        melee = create_trait("Melee")
        response = client.post(
            "/n26/authoring/modifiers/",
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

    def test_more_modifiers_do_not_mean_more_queries(
        self, author, client, default_pack, django_assert_num_queries
    ):
        """The page reads every modifier's sentence and counts every
        carrier. Both are gathered for the whole page at once, so a pack
        that grows costs rows, not round trips."""
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
