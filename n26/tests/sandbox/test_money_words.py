"""Guard distinct terminology for current prices, recorded payments and rating
contributions in stored fields and display structures. Moves preserve recorded rating
even when the current price differs. Discover models and dataclasses so new fields are
covered automatically.

Keep author-only qualifiers and option-group labels out of player display structures and
rendered cards.
"""

import dataclasses
import inspect

import pytest
from django.apps import apps

from n26.core import browse, card, hire, listing, notes, owned, preview, render

#: Display-structure modules, including author previews that use the same card shapes.
PLAYER_FACING = (render, hire, browse, card, listing, notes, owned, preview)

#: N26 apps whose stored fields use the same vocabulary.
OUR_APPS = ("library", "n26")

#: Ambiguous field and property names.
BANNED = ("cost",)

#: Precise alternatives included in validation failures.
INSTEAD = "rating (contributed, pinned), price/credits (asked), paid (settled)"


def structures():
    """Discover dataclasses defined by the player-facing modules."""
    for module in PLAYER_FACING:
        for _, thing in inspect.getmembers(module, inspect.isclass):
            if dataclasses.is_dataclass(thing) and thing.__module__ == module.__name__:
                yield thing


def names_of(structure):
    """Return dataclass field names and readable property names."""
    return [field.name for field in dataclasses.fields(structure)] + [
        name
        for name, attribute in vars(structure).items()
        if isinstance(attribute, property)
    ]


def stored_models():
    """Discover every model in the N26 apps."""
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
    """Require known models and structures so empty discovery cannot pass the guard."""
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


# Qualifiers distinguish same-named content for authors and must not become
# player-facing names.

#: Author-facing property permitted to expose a qualifier.
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


# Option-group names are author labels. Player displays use grouping and option labels
# without adding the internal group name.


def hire_entry_with_a_labelled_set():
    """Use a distinctive option-group label so the search cannot match unrelated template
    or price text.
    """
    from django.contrib.auth.models import User  # noqa: F401

    from n26.core.hire import build_hire_entry
    from n26.library.authoring import (
        create_gang_type,
        create_option_group,
        create_profile,
        create_wargear,
        offer_option,
    )
    from n26.library.models import ProfileType
    from n26.library.standard_content import STANDARD_CONTENT

    STANDARD_CONTENT["model-characteristics"].create()
    gang_type = create_gang_type("Van Saar")
    profile = create_profile(
        "Arachni-Rig", ProfileType.objects.get(name="Fighter"), gang_type, price=275
    )
    grenades = create_option_group(profile, SET_LABEL, choose="any")
    offer_option(
        profile, "Rad gun", price=35, thing=create_wargear("Rad gun"), group=grenades
    )
    return build_hire_entry(profile)


#: Distinctive author-only group label for leakage checks.
SET_LABEL = "Weapon hardpoints (author's shorthand)"


def every_value_in(thing, seen=None):
    """Walk every value in nested dataclasses and containers, with cycle detection, so
    added fields are covered automatically.
    """
    seen = set() if seen is None else seen
    if id(thing) in seen:
        return
    seen.add(id(thing))
    yield thing
    if dataclasses.is_dataclass(thing) and not isinstance(thing, type):
        for field in dataclasses.fields(thing):
            yield from every_value_in(getattr(thing, field.name), seen)
    elif isinstance(thing, (list, tuple, set)):
        for item in thing:
            yield from every_value_in(item, seen)
    elif isinstance(thing, dict):
        for item in thing.values():
            yield from every_value_in(item, seen)


@pytest.mark.django_db
def test_no_player_facing_structure_carries_a_set_label():
    """Recursively inspect the hire structure for OptionGroup objects or the author-only
    label.
    """
    from n26.library.models import OptionGroup

    entry = hire_entry_with_a_labelled_set()
    offenders = [
        value
        for value in every_value_in(entry)
        if isinstance(value, OptionGroup)
        or (isinstance(value, str) and SET_LABEL in value)
    ]
    assert not offenders, (
        f"{offenders} would put an author's label for a set in front of "
        f"the player picking from it. A set is shown as grouping — the "
        f"controls together, a rule between sets — and never as a heading."
    )


@pytest.mark.django_db
def test_a_hire_row_shows_the_answers_and_not_the_question():
    """Render option labels while omitting the author-only group name."""
    from django.template import Context, Template
    from django_cotton.compiler_regex import CottonCompiler

    entry = hire_entry_with_a_labelled_set()
    # Compile Cotton tags explicitly because Template constructed from a string does not
    # pass through the Cotton template loader.
    drawn = Template(
        CottonCompiler().process(
            '<c-n26.profile-picker.row :entry="entry" value="rig" />'
        )
    ).render(Context({"entry": entry}))
    assert "Rad gun" in drawn
    assert "Choose any" in drawn
    assert SET_LABEL not in drawn


@pytest.mark.django_db
def test_a_qualified_thing_draws_without_its_qualifier():
    """Render the weapon name without its author-only qualifier."""
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
