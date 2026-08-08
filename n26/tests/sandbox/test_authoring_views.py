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
    def test_every_leaf_page_renders(self, kind, author, client, default_pack):
        response = client.get(f"/n26/authoring/{kind}/")
        assert response.status_code == 200

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


class TestCreatingALeaf:
    def test_the_form_shows_the_models_own_words(self, author, client, default_pack):
        from n26.library.models import Rule

        body = client.get("/n26/authoring/rule/").content.decode()
        assert str(Rule._meta.get_field("annotation").help_text) in body

    def test_a_valid_submit_performs_the_verb(self, author, client, default_pack):
        from n26.library.models import Subtype

        response = client.post("/n26/authoring/subtype/", {"name": "Mounted"})
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
            "/n26/authoring/wargear/",
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
            "/n26/authoring/rule/",
            {"name": "Lead Ritual", "annotation": "Leader only"},
        )
        assert str(Rule.objects.get(name="Lead Ritual")) == "Lead Ritual (Leader only)"

    def test_a_duplicate_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.models import Subtype

        client.post("/n26/authoring/subtype/", {"name": "Mounted"})
        response = client.post("/n26/authoring/subtype/", {"name": "Mounted"})

        assert response.status_code == 200  # back on the form, not a 500
        assert "already exists in this pack" in response.content.decode()
        assert Subtype.objects.filter(name="Mounted").count() == 1

    def test_a_missing_name_refuses_in_words(self, author, client, default_pack):
        from n26.library.models import Counter

        response = client.post("/n26/authoring/counter/", {"name": ""})
        assert response.status_code == 200
        assert "required" in response.content.decode()
        assert Counter.objects.count() == 0


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
            "/n26/authoring/section/", {"name": "Ranged Weapons", "position": "0"}
        )
        heading = Section.objects.get(name="Ranged Weapons")

        client.post(
            "/n26/authoring/category/",
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

        client.post("/n26/authoring/lasting-effect/", {"name": "Humiliated"})
        assert LastingEffect.objects.filter(name="Humiliated").exists()

        # One kind, two words: the label is the profile type's own.
        assert fighter_type.lasting_effect_term == "Injury"
        assert vehicle_type.lasting_effect_term == "Damage"


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
            "/n26/authoring/subtype/",
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

        client.post("/n26/authoring/subtype/", {"name": "Mounted"})
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
        body = client.get("/n26/authoring/").content.decode()
        # Every family has pages now, and they read in declaration order.
        positions = [
            body.index(f"<h2>{label}</h2>")
            for label in ("Base", "Model", "Gear", "Gang")
        ]
        assert positions == sorted(positions)
        # A kind sits under its family.
        assert body.index("<h2>Gear</h2>") < body.index("wargear")
        assert body.index("<h2>Gang</h2>") < body.index("archetype")

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
        body = client.get("/n26/authoring/subtype/").content.decode()
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
            "/n26/authoring/hidden/",
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

        client.post("/n26/authoring/archetype/", {"name": "Brawler"})
        client.post("/n26/authoring/affiliation/", {"name": "Clan House"})
        assert Archetype.objects.filter(name="Brawler").exists()
        assert Affiliation.objects.filter(name="Clan House").exists()

    def test_a_specialisation(self, author, client, default_pack):
        from n26.library.models import Specialisation

        client.post("/n26/authoring/specialisation/", {"name": "Medicate"})
        assert Specialisation.objects.filter(name="Medicate").exists()

    def test_a_skill_tree_needs_the_set_it_stands_for(
        self, author, client, default_pack
    ):
        from n26.library.authoring import create_category
        from n26.library.models import SkillTree

        agility = create_category("Skills", "Agility")
        response = client.post(
            "/n26/authoring/skill-tree/",
            {"name": "Agility", "category": str(agility.pk)},
        )
        assert response.status_code == 302
        assert SkillTree.objects.get(name="Agility").category == agility

        # The token is meaningless without its home, so the form insists.
        response = client.post("/n26/authoring/skill-tree/", {"name": "Nowhere"})
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
            "/n26/authoring/weapon/",
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
            # The platform's form renderer draws the label (no ":" suffix,
            # its own classes) — assert the words, not the chrome.
            assert f">{short}</label>" in body
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
            "/n26/authoring/weapon-accessory/",
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
            "/n26/authoring/weapon-accessory/",
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
                "/n26/authoring/weapon/",
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
                "/n26/authoring/subtype/", {"name": "Mounted", "qualifier": "beasts"}
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
            "/n26/authoring/weapon/",
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
            "/n26/authoring/gang-type/",
            {"name": "Escher", "starting_credits": "1000"},
        )
        escher = GangType.objects.get(name="Escher")
        response = client.post(
            "/n26/authoring/profile/",
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
            "/n26/authoring/gang-type/",
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
            "/n26/authoring/collection/", {"name": "House Escher Equipment List"}
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
        body = client.get("/n26/authoring/profile/").content.decode()
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
            "/n26/authoring/profile/",
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

        response = client.post("/n26/authoring/collection/", {"name": "House List"})
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
            "/n26/authoring/weapon/",
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
