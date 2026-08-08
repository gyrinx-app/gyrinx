"""Foundations: the things content is built from, and the seeds.

Stats, statline shapes and profile types are nobody's authoring
decision — the rulebook fixes them, and nothing else can be built
until they exist. So they are created from a page rather than typed, and
these tests hold the seeds to what makes buttons safer than a data
migration:

* a seed says honestly whether it has been created, including *partly*;
* creating twice is harmless, so a half-built library can be topped up;
* creating shares definitions with nothing invented — a weapon's
  Strength is the fighter's Strength, matched not duplicated;
* what a seed creates is what the whole app already expects, so a card
  rendered on seeded content reads exactly as a card on fixtures.
"""

import pytest
from django.contrib.auth.models import User

from n26.library.models import ProfileType, Stat, StatlineType, Subtype
from n26.library.standard_content import (
    MODEL_CHARACTERISTICS,
    MODEL_STATLINE,
    STANDARD_CONTENT,
    WEAPON_STATLINE,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def author(client):
    user = User.objects.create_user("author", is_staff=True)
    client.force_login(user)
    return user


class TestTheSeedsThemselves:
    def test_there_is_something_to_check(self):
        assert {"model-characteristics", "weapon-characteristics"} <= set(
            STANDARD_CONTENT
        )

    @pytest.mark.parametrize("key", sorted(STANDARD_CONTENT), ids=str)
    def test_an_empty_library_reports_missing(self, key, default_pack):
        seed = STANDARD_CONTENT[key]
        present, total = seed.check()
        assert (present, seed.status()) == (0, "missing")
        assert total > 0

    @pytest.mark.parametrize("key", sorted(STANDARD_CONTENT), ids=str)
    def test_creating_makes_it_complete(self, key, default_pack):
        seed = STANDARD_CONTENT[key]
        seed.create()
        present, total = seed.check()
        assert present == total
        assert seed.status() == "complete"

    @pytest.mark.parametrize("key", sorted(STANDARD_CONTENT), ids=str)
    def test_creating_twice_changes_nothing(self, key, default_pack):
        seed = STANDARD_CONTENT[key]
        seed.create()
        after_once = seed.check()
        counts = {
            model: model.objects.count()
            for model in (Stat, StatlineType, ProfileType, Subtype)
        }

        seed.create()

        assert seed.check() == after_once
        assert {model: model.objects.count() for model in counts} == counts

    def test_a_half_built_library_is_topped_up(self, default_pack):
        """The case a data migration handles badly: some of it is
        already there, by hand or from an earlier run."""
        from n26.library.authoring import create_stat

        create_stat("M", "Movement", is_inches=True)
        seed = STANDARD_CONTENT["model-characteristics"]
        assert seed.status() == "incomplete"

        seed.create()

        assert seed.status() == "complete"
        assert Stat.objects.filter(full_name="Movement").count() == 1


class TestWhatTheSeedsCreate:
    def test_the_model_characteristics_are_the_thirteen(self, default_pack):
        STANDARD_CONTENT["model-characteristics"].create()

        shape = StatlineType.objects.get(name=MODEL_STATLINE)
        printed = [type_stat.short_name for type_stat in shape.stats.all()]
        assert printed == [short for short, _, _, _ in MODEL_CHARACTERISTICS]
        assert printed[:3] == ["M", "WS", "BS"]
        assert printed[-4:] == ["Ld", "Cl", "Wil", "Int"]

        # The head stats are plain numbers, never roll targets.
        for short in ("Ld", "Cl", "Wil", "Int"):
            assert not Stat.objects.get(short_name=short).is_target

    def test_the_closed_set_is_stated_once(self):
        """The model owns which Types exist; standard content only says
        what each calls a lasting effect. If those two ever disagreed,
        a Type would be created that the database then refused."""
        from n26.library.models.profile import TYPE_NAMES
        from n26.library.standard_content import LASTING_EFFECT_TERMS

        assert set(LASTING_EFFECT_TERMS) == set(TYPE_NAMES)

    def test_both_profile_types_with_their_own_word(self, default_pack):
        STANDARD_CONTENT["model-characteristics"].create()

        fighter = ProfileType.objects.get(name="Fighter")
        vehicle = ProfileType.objects.get(name="Vehicle")
        assert fighter.lasting_effect_term == "Injury"
        assert vehicle.lasting_effect_term == "Damage"
        # One shape serves both; the Type line tells them apart.
        assert fighter.statline_type == vehicle.statline_type

    def test_the_weapon_shape_reuses_the_fighters_strength(self, default_pack):
        """Stat definitions are shared across statline types by design,
        so creating both must not fork Strength in two."""
        STANDARD_CONTENT["model-characteristics"].create()
        STANDARD_CONTENT["weapon-characteristics"].create()

        assert Stat.objects.filter(full_name="Strength").count() == 1
        weapon = StatlineType.objects.get(name=WEAPON_STATLINE)
        printed = [t.short_name for t in weapon.stats.all()]
        assert printed == ["SR", "LR", "S", "AP", "L"]
        # Note the honest consequence: one shared row carries one
        # abbreviation, so a weapon table prints the fighter's "S" where
        # the book prints "Str". Fixing that means the abbreviation
        # belongs to the *shape* rather than the characteristic — a
        # short name on StatlineTypeStat — which is a decision, not a
        # bug, and is not made here.

    def test_the_core_subtypes_arrive_named(self, default_pack):
        STANDARD_CONTENT["core-subtypes"].create()
        names = set(Subtype.objects.values_list("name", flat=True))
        assert {"Leader", "Champion", "Ganger", "Wyrd", "Mounted"} <= names
        assert {"Walker", "Wheeled", "Skimmer"} <= names  # vehicles too

    def test_the_gang_types_arrive_named_and_nothing_more(self, default_pack):
        """Names only — profiles, lists and rules are authored onto
        these rows later, so a fresh one carries no numbers."""
        from n26.library.models import GangType

        STANDARD_CONTENT["gang-types"].create()
        names = set(GangType.objects.values_list("name", flat=True))
        assert {"Escher", "Goliath", "Ash Waste Nomads", "Venators"} <= names
        assert GangType.objects.count() == 17
        assert GangType.objects.get(name="Escher").starting_credits is None

    def test_the_specialisations_arrive_granting_their_skills(self, default_pack):
        """The Specialist's eight fields, each wired to the one skill it
        grants — the pair is the content, so a row without its grant is
        only half created."""
        from n26.library.models import Specialisation

        STANDARD_CONTENT["skills"].create()
        STANDARD_CONTENT["specialisations"].create()

        assert set(Specialisation.objects.values_list("name", flat=True)) == {
            "Heavy",
            "Gunner",
            "Gunslinger",
            "Scout",
            "Sniper",
            "Brawler",
            "Medic",
            "Tech",
        }
        granted = {
            row.name: [str(modifier.effect.skill) for modifier in row.modifiers.all()]
            for row in Specialisation.objects.all()
        }
        assert granted["Gunner"] == ["Hip-shooting"]
        assert granted["Medic"] == ["Medicate"]
        assert granted["Heavy"] == ["Bulging Biceps"]

    def test_specialisations_create_the_skills_they_grant(self, default_pack):
        """Created alone — no skills yet — it still completes, because a
        specialisation without its skill is half a thing and the seed
        owns that dependency rather than the order of button presses."""
        from n26.library.models import Skill, Specialisation

        seed = STANDARD_CONTENT["specialisations"]
        seed.create()

        assert seed.status() == "complete"
        assert Specialisation.objects.count() == 8
        assert Skill.objects.filter(name="Hip-shooting").exists()


class TestThePage:
    def test_it_shows_status_before_and_after(self, author, client, default_pack):
        body = client.get("/n26/authoring/foundations/").content.decode()
        assert "missing" in body
        assert "Model characteristics" in body

        # The button's own payload. This test once posted a key the view
        # never read and still passed, because the old inline stylesheet
        # happened to contain the word "complete" — the page said nothing
        # of the sort. The styles are the design system's now, so the
        # assertion finally means what it says.
        client.post("/n26/authoring/foundations/", {"create": "model-characteristics"})
        body = client.get("/n26/authoring/foundations/").content.decode()
        assert "complete" in body
        assert "Fighter" in body  # the profile type it made

    def test_creating_needs_a_real_seed(self, author, client, default_pack):
        assert (
            client.post(
                "/n26/authoring/foundations/", {"do": "seed:nonsense"}
            ).status_code
            == 404
        )

    def test_it_shows_the_types_it_created(self, author, client, default_pack):
        """They cannot be authored, so this is the only place an author
        sees that they are there — and that there are only two."""
        STANDARD_CONTENT["model-characteristics"].create()
        body = client.get("/n26/authoring/foundations/").content.decode()
        assert "Fighter" in body and "Vehicle" in body
        assert "lasting injury" in body and "lasting damage" in body
        assert "Fighter or Vehicle and nothing else" in body

    def test_it_links_to_each_kinds_own_page(self, author, client, default_pack):
        body = client.get("/n26/authoring/foundations/").content.decode()
        for kind in ("stat", "statline-type"):
            assert f'href="/n26/authoring/{kind}/"' in body


class TestTheFoundationPages:
    """Each foundation kind is an ordinary page, like every other kind."""

    def test_a_stat_has_its_own_page(self, author, client, default_pack):
        client.post(
            "/n26/authoring/stat/",
            {"short_name": "Ht", "full_name": "Heat"},
        )
        assert Stat.objects.get(full_name="Heat").short_name == "Ht"

    def test_a_type_cannot_be_invented(self, author, client, default_pack):
        """A model's Type is Fighter or Vehicle and nothing else, so
        there is no page that would offer a third. Ganger and Champion
        are Subtypes; a sentry gun is a Vehicle."""
        assert client.get("/n26/authoring/profile-type/").status_code == 404
        assert set(ProfileType.objects.values_list("name", flat=True)) == set()

        STANDARD_CONTENT["model-characteristics"].create()
        assert set(ProfileType.objects.values_list("name", flat=True)) == {
            "Fighter",
            "Vehicle",
        }

    def test_a_statline_shape_is_built_a_stat_at_a_time_in_order(
        self, author, client, default_pack
    ):
        """Print order is the whole point of a shape, and a multi-select
        cannot express it — so the shape is created bare and its stats
        are added one by one, each landing at the end."""
        response = client.post("/n26/authoring/statline-type/", {"name": "Vehicle"})
        shape = StatlineType.objects.get(name="Vehicle")
        assert response["Location"] == f"/n26/authoring/statline-type/{shape.pk}/"

        from n26.library.authoring import create_stat

        for short, full in (("T", "Toughness"), ("W", "Wounds"), ("Sv", "Save")):
            client.post(
                f"/n26/authoring/statline-type/{shape.pk}/",
                {"stat": str(create_stat(short, full).pk)},
            )

        assert [t.short_name for t in shape.stats.all()] == ["T", "W", "Sv"]

    def test_the_shape_shows_its_columns_as_it_prints_them(
        self, author, client, default_pack
    ):
        """The two display flags are the only things about a row a
        reader cannot infer, so the table says them — and does not
        prefix every row with the shape's own name."""
        from n26.library.authoring import create_stat

        client.post("/n26/authoring/statline-type/", {"name": "Model"})
        shape = StatlineType.objects.get(name="Model")
        client.post(
            f"/n26/authoring/statline-type/{shape.pk}/",
            {"stat": str(create_stat("M", "Movement", is_inches=True).pk)},
        )
        client.post(
            f"/n26/authoring/statline-type/{shape.pk}/",
            {
                "stat": str(create_stat("Ld", "Leadership").pk),
                "is_highlighted": "on",
                "is_first_of_group": "on",
            },
        )

        body = client.get(f"/n26/authoring/statline-type/{shape.pk}/").content.decode()
        assert "M (Movement)" in body
        assert "starts a group" in body
        assert "highlighted" in body
        assert "Model — Ld" not in body  # no redundant prefix

    def test_a_shape_can_mark_where_a_group_starts(self, author, client, default_pack):
        from n26.library.authoring import create_stat

        client.post("/n26/authoring/statline-type/", {"name": "Fighter"})
        shape = StatlineType.objects.get(name="Fighter")
        client.post(
            f"/n26/authoring/statline-type/{shape.pk}/",
            {
                "stat": str(create_stat("Ld", "Leadership").pk),
                "is_highlighted": "on",
                "is_first_of_group": "on",
            },
        )
        (row,) = shape.stats.all()
        assert row.is_highlighted and row.is_first_of_group

    def test_staff_only(self, client, default_pack):
        assert client.get("/n26/authoring/foundations/").status_code == 302


class TestSeededContentIsUsable:
    def test_a_weapon_authored_on_seeded_stats_renders(
        self, author, client, default_pack
    ):
        """End to end from nothing: create, author a weapon, read the card."""
        from n26.core.render import render_gang
        from n26.library.authoring import create_profile, create_trait, set_statline
        from n26.library.models import Weapon
        from n26.tests.sandbox.actions import found_gang, give_weapon, hire

        STANDARD_CONTENT["model-characteristics"].create()
        STANDARD_CONTENT["weapon-characteristics"].create()

        weapon_shape = StatlineType.objects.get(name=WEAPON_STATLINE)
        client.post(
            "/n26/authoring/weapon/",
            {
                "name": "Lasgun",
                "slots": "1",
                "statline_type": str(weapon_shape.pk),
                "price": "15",
                "trade_point_price": "0",
            },
        )
        lasgun = Weapon.objects.get(name="Lasgun")
        client.post(
            f"/n26/authoring/weapon/{lasgun.pk}/",
            {
                "name": "Standard",
                "price": "0",
                "trade_point_price": "0",
                "traits": [str(create_trait("Plentiful").pk)],
                "short_range": "12",
                "long_range": "24",
                "strength": "3",
                "armour_piercing": "-",
                "lethality": "1",
            },
        )

        # A fighter on the seeded shape, holding the authored weapon.
        from n26.library.models import GangType

        gang_type = GangType.objects.create(name="Escher")
        ganger = create_profile(
            "Gang Sister", ProfileType.objects.get(name="Fighter"), gang_type, price=50
        )
        set_statline(
            ganger,
            movement=5,
            weapon_skill=4,
            ballistic_skill=4,
            strength=3,
            toughness=3,
            wounds=1,
            initiative=4,
            attacks=1,
            save=6,
            leadership=6,
            cool=6,
            willpower=6,
            intelligence=6,
        )
        gang = found_gang(
            "The Seeded",
            gang_type,
            owner=User.objects.create_user("seeder"),
            budget=500,
        )
        fighter = hire(gang, ganger, "Yolanda", paid=50)
        give_weapon(fighter, lasgun, paid=15)

        from n26.core.render_text import render_model_card

        (card,) = render_gang(gang).models
        text = "\n".join(render_model_card(card))
        print("\n" + text)
        assert "Ld" in text and "6" in text  # head stats, plain numbers
        assert "Lasgun" in text
        assert '12"' in text  # the seeded stat's own formatting


class TestTheSkills:
    """Every skill the core rules name, in its set and at the number it
    is rolled on. Names only — what a skill does is the book's."""

    def test_the_six_sets_and_the_inherent_one(self, default_pack):
        from n26.library.models import Category, Section

        STANDARD_CONTENT["skills"].create()

        section = Section.objects.get(name="Skills")
        sets = list(
            Category.objects.filter(section=section).values_list("name", flat=True)
        )
        assert sets == [
            "Agility",
            "Brawn",
            "Combat",
            "Cunning",
            "Savant",
            "Shooting",
            "Inherent",
        ]

    def test_a_skill_knows_its_set_and_its_d6_number(self, default_pack):
        from n26.library.models import Skill

        STANDARD_CONTENT["skills"].create()

        catfall = Skill.objects.get(name="Catfall")
        assert catfall.category.name == "Agility"
        assert catfall.position == 1  # rolled on a 1
        assert Skill.objects.get(name="Sprint").position == 6

        # A set reads back in the order the table prints it.
        agility = Skill.objects.filter(category__name="Agility").order_by("position")
        assert [skill.name for skill in agility] == [
            "Catfall",
            "Clamber",
            "Dodge",
            "Mighty Leap",
            "Spring Up",
            "Sprint",
        ]

    def test_the_inherent_skills_are_rolled_for_on_no_table(self, default_pack):
        """A rule grants them, so they carry no D6 number — Immovable
        Brutes grants Juggernaut."""
        from n26.library.models import Skill

        STANDARD_CONTENT["skills"].create()

        juggernaut = Skill.objects.get(name="Juggernaut")
        assert juggernaut.category.name == "Inherent"
        assert juggernaut.position == 0

    def test_all_thirty_nine(self, default_pack):
        from n26.library.models import Skill

        STANDARD_CONTENT["skills"].create()
        assert Skill.objects.count() == 39  # 6 sets of 6, plus 3 inherent

    def test_it_reports_and_tops_up_like_the_rest(self, default_pack):
        from n26.library.authoring import create_skill

        item = STANDARD_CONTENT["skills"]
        assert item.status() == "missing"

        create_skill("Catfall")  # someone got there first
        assert item.status() == "incomplete"

        item.create()
        assert item.status() == "complete"
        item.create()  # twice is harmless
        assert item.status() == "complete"
