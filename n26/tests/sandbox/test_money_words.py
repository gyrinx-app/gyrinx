"""One quantity, one word — enforced.

There are two different numbers in this system and they are easy to
confuse, because for one instant they are equal:

**A price** is what a surface asks you to pay, right now: a catalogue
number, an equipment list's override, an option's surcharge. It lives on
content and on shop structures, and it is answered fresh every time
anyone asks.

**A rating** is what an assignment contributed to a model's worth. It is
copied from the price at the moment of purchase and then **pinned
forever** — moving the thing to a fighter who would have paid less never
re-prices it. So
from the instant after a purchase, the two numbers are free to disagree,
and a discounted item disagrees immediately.

The word **cost** is banned outright, because it names either one. It
already caused a real bug: a card line read a rating contribution of 0
and printed "(free)" next to the Sanctioner's 50-credit choke gas
grenades, which the hire package had paid for. The number was right; the
word was a lie. Renaming was the fix, and this test is what stops it
coming back — including in models and structures nobody has written yet,
since it discovers them rather than listing them.

The ban covers **stored fields as well as render structures**, because
the muddle started in the database: the mixin stored a ``cost`` while
``Profile`` stored a ``rating`` that was really the fighter's price, and
those two names then propagated in opposite directions through every
layer above. Both are ``price`` now, and Profile's two fields collapsed
into the mixin's one.
"""

import dataclasses
import inspect

import pytest
from django.apps import apps

from n26.core import browse, card, hire, listing, notes, owned, preview, render

#: Every module whose structures a player-facing surface reads.
#: ``preview`` is player-adjacent — the scratch card an author reads is
#: the same card a player will — so its structures keep the same words.
PLAYER_FACING = (render, hire, browse, card, listing, notes, owned, preview)

#: Apps whose stored fields the rule covers — ours, not Django's own.
OUR_APPS = ("library", "n26")

#: Words that name two different quantities, so may name neither.
BANNED = ("cost",)

#: The honest words, for the failure message.
INSTEAD = "rating (contributed, pinned), price/credits (asked), paid (settled)"


def structures():
    """Dataclasses defined in the player-facing modules, found not listed."""
    for module in PLAYER_FACING:
        for _, thing in inspect.getmembers(module, inspect.isclass):
            if dataclasses.is_dataclass(thing) and thing.__module__ == module.__name__:
                yield thing


def names_of(structure):
    """Field and property names — a property is just as readable as a field."""
    return [field.name for field in dataclasses.fields(structure)] + [
        name
        for name, attribute in vars(structure).items()
        if isinstance(attribute, property)
    ]


def stored_models():
    """Our Django models — where the muddle started, so where it is checked."""
    for app in OUR_APPS:
        yield from apps.get_app_config(app).get_models()


def why(named, offenders):
    return (
        f"{named} has {', '.join(offenders)}. "
        f"'Cost' means both what a thing is worth and what it added to a "
        f"rating, and those part company the moment anything is discounted. "
        f"Say which one you mean: {INSTEAD}."
    )


def offending(names):
    return [name for name in names if any(word in name for word in BANNED)]


def test_there_is_something_to_check():
    """A guard that discovers nothing guards nothing."""
    found = {structure.__name__ for structure in structures()}
    assert {
        "ModelCard",
        "WeaponLine",
        "WeaponProfileLine",
        "HireOption",
        "OwnedThing",
    } <= found
    stored = {model.__name__ for model in stored_models()}
    assert {"Weapon", "Profile", "CollectionEntry", "LedgerEntry"} <= stored


@pytest.mark.parametrize("structure", list(structures()), ids=lambda s: s.__name__)
def test_a_render_structure_says_rating_or_price_but_never_cost(structure):
    assert not offending(names_of(structure)), why(
        structure.__name__, offending(names_of(structure))
    )


@pytest.mark.django_db
@pytest.mark.parametrize("model", list(stored_models()), ids=lambda m: m.__name__)
def test_a_stored_field_says_rating_or_price_but_never_cost(model):
    names = [field.name for field in model._meta.get_fields()]
    assert not offending(names), why(model.__name__, offending(names))


# --- The qualifier never reaches a player -----------------------------------
#
# The qualifier exists to tell two same-named things apart *for authors*.
# If it could leak into anything a player reads it would become a second
# name by accident — the exact failure it exists to prevent — so this is
# guarded structurally, not by convention.

#: The one property allowed to show it.
AUTHORING_ONLY = "authoring_label"


def test_no_player_facing_structure_carries_a_qualifier():
    offenders = [
        f"{structure.__name__}.{name}"
        for structure in structures()
        for name in names_of(structure)
        if "qualifier" in name
    ]
    assert not offenders, (
        f"{', '.join(offenders)} would put an author's disambiguator in "
        f"front of a player. The qualifier belongs to authoring alone — "
        f"see Assignable.{AUTHORING_ONLY}."
    )


@pytest.mark.django_db
def test_a_qualified_thing_draws_without_its_qualifier():
    """The end of the chain: a card built from a qualified weapon must
    read exactly as one built from an unqualified one."""
    from django.contrib.auth.models import User

    from n26.core.render import build_model_card
    from n26.core.render_text import render_model_card
    from n26.library.authoring import create_weapon
    from n26.library.models import GangType, ProfileType, StatlineType
    from n26.library.standard_content import MODEL_STATLINE, STANDARD_CONTENT
    from n26.tests.sandbox.actions import found_gang, give_weapon, hire

    STANDARD_CONTENT["model-characteristics"].create()
    gang_type = GangType.objects.create(name="Goliath")
    from n26.library.authoring import create_profile, set_statline

    profile = create_profile(
        "Bruiser", ProfileType.objects.get(name="Fighter"), gang_type, price=50
    )
    set_statline(profile, movement=4, strength=4, toughness=4)
    assert StatlineType.objects.filter(name=MODEL_STATLINE).exists()

    jaws = create_weapon(
        "Ferocious jaws", qualifier="Sumpkroc", profiles=[("Standard", 0)]
    )
    gang = found_gang(
        "The Named", gang_type, owner=User.objects.create_user("namer"), budget=200
    )
    fighter = hire(gang, profile, "Krush", paid=50)
    give_weapon(fighter, jaws, paid=0)

    text = "\n".join(render_model_card(build_model_card(fighter)))
    assert "Ferocious jaws" in text
    assert "Sumpkroc" not in text
