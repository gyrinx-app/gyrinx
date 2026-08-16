"""Specs — each verb's parameters as data, proven against real objects.

Step 1 of design/authoring-build-plan.md. Three kinds of test here:

* **The discovering guard** (the money-words pattern): every
  ``targets_*``/``ef_*``/``op_*`` verb in ``n26.library.authoring`` must
  have a spec, and a spec may only name parameters the verb actually
  takes — found by inspection, never listed, so a new verb without a
  spec fails the suite rather than shipping formless.
* **Help is sourced, never written**: every sourced field's help must
  be *literally* the model field's ``help_text``, plus a few literal
  pins so a source can't quietly go missing or drift.
* **Every spec compiles a named example object**: the
  form-shaped data replicating something an example suite built — the
  Brawler leader row, the XP-75 promotion, the Trazior deployer —
  compiles through the spec and must say exactly what that object
  says. Where the example is cheap to rebuild, the spec's output is
  compared against the very object the suite's own actions create.
"""

import inspect

import pytest

from n26.library import authoring
from n26.library.specs import Conditions, specs
from n26.tests.sandbox.actions import (
    create_collection,
    create_counter,
    create_rule,
    create_subtype,
    create_trait,
    section_of,
)
from n26.tests.sandbox.actions import (
    targets_model as sandbox_targets_model,
)

pytestmark = pytest.mark.django_db

#: The verb prefixes the guard sweeps — the prefix says when it happens.
PREFIXES = ("targets_", "ef_", "op_")


def prefixed_verbs():
    """Every authored scope and effect verb, discovered not listed."""
    return [
        thing
        for name, thing in inspect.getmembers(authoring, inspect.isfunction)
        if name.startswith(PREFIXES)
    ]


class TestTheDiscoveringGuard:
    def test_there_is_something_to_check(self):
        """A guard that discovers nothing guards nothing."""
        found = {verb.__name__ for verb in prefixed_verbs()}
        assert {"targets_model", "ef_adds", "ef_offers_choice", "op_adds_model"} <= (
            found
        )

    @pytest.mark.parametrize("verb", prefixed_verbs(), ids=lambda v: v.__name__)
    def test_every_prefixed_verb_has_a_spec(self, verb):
        assert verb.__name__ in specs(), (
            f"{verb.__name__} is an authoring verb with no spec — no form "
            f"can be generated for it. Add one to library.specs."
        )

    @pytest.mark.parametrize("name", list(specs()), ids=str)
    def test_a_spec_only_names_parameters_its_verb_takes(self, name):
        spec = specs()[name]
        takes = set(inspect.signature(spec.verb).parameters)
        named = set(spec.fields)
        # A Conditions field fills the verb's *conditions varargs.
        for field_name, kind in spec.fields.items():
            if isinstance(kind, Conditions):
                named.discard(field_name)
                named.add("conditions")
        assert named <= takes, (
            f"The {name} spec names {sorted(named - takes)}, which "
            f"{name}() does not take. A spec describes the verb; it "
            f"cannot invent parameters."
        )


class TestVerbTablesCoverTheColumns:
    """``_scope_verb`` and ``_effect_verb`` read stored rows back to the
    verb an author picked, ending in a bare lookup over these tables —
    a scope or effect model missing from its table would 500 every page
    that names a modifier's kind, so drift is refused here."""

    def test_every_scope_column_is_covered(self):
        from n26.library.forms import SCOPE_MODELS
        from n26.library.models import Modifier
        from n26.library.models.modifier import SCOPE_FIELDS

        columns = {
            Modifier._meta.get_field(name).related_model.__name__
            for name in SCOPE_FIELDS
        }
        assert columns == set(SCOPE_MODELS.values())

    def test_every_effect_column_is_covered(self):
        from n26.library.forms import EFFECT_MODELS
        from n26.library.models import Modifier
        from n26.library.models.modifier import EFFECT_FIELDS

        columns = {
            Modifier._meta.get_field(name).related_model.__name__
            for name in EFFECT_FIELDS
        }
        assert columns == set(EFFECT_MODELS.values())

    def test_every_table_verb_has_a_spec(self):
        from n26.library.forms import EFFECT_MODELS, SCOPE_MODELS

        assert set(SCOPE_MODELS) <= set(specs())
        assert set(EFFECT_MODELS) <= set(specs())


def scope_conditions():
    """Every ``(scope model, relation)`` a condition row hangs on."""
    from n26.library.models import Modifier
    from n26.library.models.modifier import SCOPE_FIELDS

    found = []
    for field in SCOPE_FIELDS:
        model = Modifier._meta.get_field(field).related_model
        found.extend((model, relation) for relation in getattr(model, "CONDITIONS", ()))
    return found


class TestAScopeCanBeReadBackAsChips:
    """A form opened on a scope has to find the rows narrowing it, and
    it finds them by name: the relation a condition hangs on is the same
    word as the verb that builds it. Break that pairing and a modifier's
    page offers to save it with its narrowing quietly dropped."""

    def test_there_is_something_to_check(self):
        assert scope_conditions()

    @pytest.mark.parametrize(
        "model, relation", scope_conditions(), ids=lambda part: str(part)
    )
    def test_a_conditions_relation_is_named_after_its_verb(self, model, relation):
        assert relation in specs(), (
            f"{model.__name__} hangs conditions on {relation!r}, but no verb "
            f"is called that. The authoring pages read a scope's narrowing "
            f"back through this name — rename one to match the other."
        )


class TestHelpIsSourcedNeverWritten:
    def all_sourced_fields(self):
        return [
            (spec_name, field_name, kind)
            for spec_name, spec in specs().items()
            for field_name, kind in spec.fields.items()
            if getattr(kind, "source", None) is not None
        ]

    def test_every_sourced_help_is_literally_the_model_fields_words(self):
        checked = 0
        for spec_name, field_name, kind in self.all_sourced_fields():
            model, model_field = kind.source
            assert kind.help == str(model._meta.get_field(model_field).help_text), (
                f"{spec_name}.{field_name} paraphrases {model.__name__}."
                f"{model_field} instead of sourcing it."
            )
            checked += 1
        assert checked >= 10  # the guard is guarding something

    def test_the_pins(self):
        """Literal pins: if a model's words change, someone chose to
        change what every admin reads."""
        assert specs()["counter_at_least"].fields["counter"].help == (
            "The counter whose value is checked."
        )
        assert specs()["ef_offers_choice"].fields["model"].choices == tuple(
            (kind, kind)
            for kind in (
                "specialisation",
                "power",
                "skill",
                "skilltree",
                "archetype",
                "affiliation",
                "subtype",
            )
        )


# --- Compiling the named example objects -----------------------------------


class TestTargetsModel:
    """Against the Outcast and counter suites' scopes."""

    def test_plain_is_cult_of_personalitys_everyone(self, default_pack):
        scope = specs()["targets_model"].compile({})
        assert str(scope) == "the model"

    def test_subtyped_is_the_brawler_leader_row(self, default_pack):
        leader = create_subtype("Outcast Leader")
        scope = specs()["targets_model"].compile(
            {"conditions": [("has_subtypes", {"subtypes": [leader]})]}
        )
        # The very row the Outcast suite builds, made its way.
        example = sandbox_targets_model(with_subtypes=[leader])
        assert str(scope) == str(example) == "Outcast Leader models"

    def test_threshold_is_the_xp_75_promotion(self, default_pack):
        xp = create_counter("XP")
        scope = specs()["targets_model"].compile(
            {"conditions": [("counter_at_least", {"counter": xp, "at_least": 75})]}
        )
        example = sandbox_targets_model(when_counter=xp, at_least=75)
        assert str(scope) == str(example) == "at XP 75+"

    def test_the_brawler_champion_row_reaches_the_model_carrying_it(self, default_pack):
        """The verb is the reach: targets_model is the bearer, and needs
        no flag to say so."""
        champion = create_subtype("Outcast Champion")
        scope = specs()["targets_model"].compile(
            {"conditions": [("has_subtypes", {"subtypes": [champion]})]}
        )
        assert str(scope) == "Outcast Champion models"
        assert scope.reach == scope.Reach.BEARER

    def test_all_models_is_its_own_verb_and_says_so(self, default_pack):
        champion = create_subtype("Outcast Champion")
        scope = specs()["targets_every_model"].compile(
            {"conditions": [("has_subtypes", {"subtypes": [champion]})]}
        )
        assert str(scope) == "Outcast Champion models (all models)"
        assert scope.reach == scope.Reach.EVERY_MODEL

    def test_a_condition_the_scope_cannot_take_refuses_in_words(self, default_pack):
        melee = create_trait("Melee")
        with pytest.raises(ValueError, match="cannot take a has_traits"):
            specs()["targets_model"].compile(
                {"conditions": [("has_traits", {"traits": [melee]})]}
            )


class TestWeaponAndPositionalScopes:
    def test_targets_weapons_is_melee_gains_backstab(self, default_pack):
        melee = create_trait("Melee")
        scope = specs()["targets_weapons"].compile(
            {"conditions": [("has_traits", {"traits": [melee]})]}
        )
        assert str(scope) == "weapons with Melee"

    def test_targets_attached_weapon_is_the_telescopic_sight(self, default_pack):
        scope = specs()["targets_attached_weapon"].compile({})
        assert str(scope) == "the weapon this is attached to"

    def test_targets_gang_is_the_affiliation_slot(self, default_pack):
        scope = specs()["targets_gang"].compile({})
        assert str(scope) == "the gang"


class TestGrantsAndRemovals:
    def test_ef_adds_is_the_cutter_granting_mounted(self, default_pack):
        mounted = create_subtype("Mounted")
        effect = specs()["ef_adds"].compile({"thing": mounted})
        assert str(effect) == "adds Mounted"

    def test_ef_adds_a_rule_is_cult_of_personality(self, default_pack):
        rule = create_rule("Cult of Personality")
        effect = specs()["ef_adds"].compile({"thing": rule})
        assert str(effect) == "adds Cult of Personality"

    def test_ef_adds_a_collection_is_the_house_escher_token(self, default_pack):
        escher_list = create_collection("House Escher Equipment List")
        effect = specs()["ef_adds"].compile({"thing": escher_list})
        assert str(effect) == "adds House Escher Equipment List"

    def test_ef_removes_is_death_of_a_leader(self, default_pack):
        ganger = create_subtype("Ganger")
        effect = specs()["ef_removes"].compile({"thing": ganger})
        assert str(effect) == "removes Ganger"


class TestStatChanges:
    def test_ef_changes_stat_is_the_arachni_rig_penalty(self, make_stat):
        attacks = make_stat("A", "Attacks")
        effect = specs()["ef_changes_stat"].compile(
            {"stat": attacks, "mode": "worsen", "amount": 1}
        )
        assert str(effect) == "worsen A by 1"


@pytest.fixture
def skills_and_powers(default_pack):
    collection = create_collection("Skills & Powers")
    return collection, {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
    }


class TestPlacements:
    def test_ef_places_is_the_brawler_grid_cell(self, skills_and_powers):
        """Brawler × Leader × Combat = Primary — the cell the Outcast
        suite's ARCHETYPES table writes."""
        from n26.tests.sandbox.actions import create_category

        collection, tiers = skills_and_powers
        combat = create_category("Skills", "Combat")
        effect = specs()["ef_places"].compile(
            {"category": combat, "section": tiers["primary"]}
        )
        assert str(effect) == "puts Combat under Primary (Skills & Powers)"

    def test_ef_places_choice_is_the_venator_rank_slot(self, skills_and_powers):
        collection, tiers = skills_and_powers
        effect = specs()["ef_places_choice"].compile({"section": tiers["primary"]})
        assert str(effect) == "puts the chosen set under Primary (Skills & Powers)"
        assert effect.the_chosen is True


class TestOffers:
    def test_the_outcast_starting_skill_offer(self, skills_and_powers):
        """ "a skill from a set that is Primary for this fighter"."""
        from n26.library.models import Skill

        collection, tiers = skills_and_powers
        effect = specs()["ef_offers_choice"].compile(
            {"model": "skill", "from_section": tiers["primary"]}
        )
        assert effect.of_kind.model_class() is Skill  # the kind name coerced
        assert str(effect) == (
            "offers a choice of skill from Primary (Skills & Powers)"
        )

    def test_the_leaders_archetype_pick_lands_on_the_gang(self, default_pack):
        effect = specs()["ef_offers_choice"].compile(
            {
                "model": "archetype",
                "label": "archetype",
                "will_be_assigned_to": "gang",
            }
        )
        assert effect.will_be_assigned_to == "gang"
        assert effect.kind_label == "Archetype"

    def test_the_venator_rank_slots_label(self, default_pack):
        effect = specs()["ef_offers_choice"].compile(
            {"model": "skilltree", "label": "skill tree 1"}
        )
        assert effect.kind_label == "Skill tree 1"


class TestChoiceLabelsReadAsLabels:
    """A slot's label is stored the way a card has to show it, so that no
    renderer has to case it on the way out: the first character is
    capitalised, and everything after it is left as the author typed it."""

    def offer(self, label):
        return specs()["ef_offers_choice"].compile(
            {"model": "archetype", "label": label}
        )

    def stored(self, label):
        """What the database ends up holding — the point being that the
        canonical value is written, not computed at read time."""
        from n26.library.models import OffersChoice

        return OffersChoice.objects.get(pk=self.offer(label).pk).label

    def test_a_lowercase_label_is_stored_capitalised(self, default_pack):
        assert self.stored("favoured archetype") == "Favoured archetype"

    def test_capitals_further_along_are_the_authors_and_stay(self, default_pack):
        """Sentence case, not title case: a name or an acronym inside a
        label was typed on purpose."""
        assert self.stored("archetype for a Clan House") == (
            "Archetype for a Clan House"
        )

    def test_a_label_that_already_reads_as_one_is_untouched(self, default_pack):
        assert self.stored("Archetype") == "Archetype"

    def test_no_label_stays_no_label(self, default_pack):
        """Blank is a real answer, not a mistake — the kind names the slot
        instead, and reads as a label too."""
        assert self.stored("") == ""
        assert self.offer("").kind_label == "Archetype"


class TestCompanionsAndStoredEffects:
    def test_ef_requires_companions_is_lead_the_masses(self, default_pack):
        champion = create_subtype("Outcast Champion")
        scum = create_subtype("Outcast Hive Scum")
        effect = specs()["ef_requires_companions"].compile(
            {"for_each": champion, "at_least": 3, "of": scum}
        )
        assert str(effect) == ("needs 3 Outcast Hive Scum for each Outcast Champion")

    def test_op_adds_model_is_the_trazior_deployer(self, make_profile):
        platform = make_profile("Trazior Pattern Sentry Gun (grenade launcher)")
        effect = specs()["op_adds_model"].compile({"profile": platform})
        assert str(effect) == "adds a Trazior Pattern Sentry Gun (grenade launcher)"
        assert effect.is_stored is True


class TestTheFullAssembly:
    def test_brawler_leader_combat_primary_all_three_rows(self, skills_and_powers):
        """The modifier row from the plan's table: WHO and WHAT each
        compiled from their spec, glued by the modifier verb, hung on
        the archetype — the composer's whole save() in miniature."""
        from n26.tests.sandbox.actions import create_archetype, create_category

        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_archetype("Brawler")

        row = authoring.modifier(
            "Brawler leader: combat primary",
            specs()["targets_model"].compile(
                {"conditions": [("has_subtypes", {"subtypes": [leader]})]}
            ),
            specs()["ef_places"].compile(
                {"category": combat, "section": tiers["primary"]}
            ),
            attach_to=brawler,
        )

        assert str(row.scope) == "Outcast Leader models"
        assert str(row.effect) == "puts Combat under Primary (Skills & Powers)"
        assert list(brawler.modifiers.all()) == [row]
