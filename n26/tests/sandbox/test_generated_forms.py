"""Specs generate authoring forms and modifier-composer panes. Validate compiled rows,
model-compatible scope/effect pairs, sourced field limits, inline creation and reusable
modifier naming using POST-shaped payloads.
"""

import inspect

import pytest

from n26.library.forms import (
    EFFECT_MODELS,
    NAME_ONLY_HELP,
    SCOPE_PRODUCES,
    ModifierComposerForm,
    condition_formset_for,
    generate_form,
)
from n26.library.specs import specs
from n26.tests.sandbox.actions import (
    create_affiliation,
    create_category,
    create_collection,
    create_subtype,
    create_trait,
    section_of,
)

pytestmark = pytest.mark.django_db


def no_conditions():
    return {
        "conditions-TOTAL_FORMS": "0",
        "conditions-INITIAL_FORMS": "0",
    }


def one_condition(kind, **fields):
    return {
        "conditions-TOTAL_FORMS": "1",
        "conditions-INITIAL_FORMS": "0",
        "conditions-0-kind": kind,
        **{f"conditions-0-{name}": value for name, value in fields.items()},
    }


@pytest.fixture
def skills_and_powers(default_pack):
    collection = create_collection("Skills & Powers")
    return collection, {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
    }


class TestTheTablesDontDrift:
    """Form lookup tables must match model acceptance and the spec registry."""

    def test_scope_produces_matches_possible_kinds(self, default_pack):
        from n26.library.models.modifier import _possible_kinds
        from n26.library.specs import specs as registry

        for verb_name, expected in SCOPE_PRODUCES.items():
            scope = registry()[verb_name].compile({})  # every scope compiles bare
            (target,) = _possible_kinds(scope)
            assert target.kind == expected, verb_name

    def test_every_effect_verb_has_a_model(self):
        effect_verbs = {name for name in specs() if name.startswith(("ef_", "op_"))}
        assert set(EFFECT_MODELS) == effect_verbs

    def test_effect_targets_match_the_models(self):
        """Check each effect’s accepted target kinds. For add/remove effects, combine bare,
        trait and rule instances because their assigned kind changes acceptance.
        """
        from n26.library.forms import EFFECT_CAN_TARGET, EFFECT_MODELS, _model_class

        effect_verbs = {name for name in specs() if name.startswith(("ef_", "op_"))}
        assert set(EFFECT_CAN_TARGET) == effect_verbs

        for verb, kinds in EFFECT_CAN_TARGET.items():
            model = _model_class(EFFECT_MODELS[verb])
            instances = [model()]
            if verb in ("ef_adds", "ef_removes"):
                # Target acceptance depends on the assigned kind.
                instances.extend([model(trait_id=1), model(rule_id=1)])
            for kind in ("model", "weapon_profile", "gang"):
                allowed = any(instance.accepts(kind) for instance in instances)
                assert (kind in kinds) == allowed, (
                    f"{verb} / {kind}: the picker table says "
                    f"{kind in kinds}, the model says {allowed} — "
                    f"update EFFECT_CAN_TARGET in n26/library/forms.py."
                )

    def test_no_two_kind_choices_read_alike(self):
        """Verbs sharing a model need distinct picker labels to identify their different
        parameters.
        """
        from n26.library.forms import _effect_choices, _scope_choices

        for choices in (_scope_choices(), _effect_choices()):
            labels = [label for _, label in choices]
            doubled = {label for label in labels if labels.count(label) > 1}
            assert not doubled, (
                f"one picker label for two verbs: {sorted(doubled)} — give "
                f"the colliding spec its own label= in specs.py"
            )


class TestGeneratedForms:
    def test_requiredness_reads_off_the_verbs_signature(self):
        form_class = generate_form(specs()["ef_requires_companions"])
        form = form_class()
        assert form.fields["for_each"].required  # no default on the verb
        assert form.fields["at_least"].required
        form_class = generate_form(specs()["ef_offers_choice"])
        form = form_class()
        assert form.fields["model"].required
        assert not form.fields["from_section"].required  # defaults to None
        assert not form.fields["label"].required

    def test_help_is_the_model_fields_words(self):
        form = generate_form(specs()["ef_offers_choice"])()
        from n26.library.models import OffersChoice

        assert form.fields["from_section"].help_text == str(
            OffersChoice._meta.get_field("from_section").help_text
        )

    def test_a_retired_choice_remains_selected_and_can_be_saved(self, default_pack):
        from n26.library.models import Affiliation, OffersChoice

        effect = OffersChoice.of(Affiliation, will_be_assigned_to="gang")
        form_class = generate_form(specs()["ef_offers_choice"])

        opened = form_class.opened_on(effect)
        assert opened["model"].value() == "affiliation"
        assert ("affiliation", "affiliation (retired)") in opened.fields[
            "model"
        ].choices

        submitted = form_class.opened_on(
            effect,
            {
                "edit-model": "affiliation",
                "edit-will_be_assigned_to": "gang",
            },
        )
        assert submitted.is_valid(), submitted.errors
        replacement = submitted.compile()
        assert replacement.of_kind.model == "affiliation"

    def test_a_valid_form_compiles_to_the_verb_call(self, skills_and_powers):
        collection, tiers = skills_and_powers
        create_category("Skills", "Combat")
        form = generate_form(specs()["ef_places_choice"])(
            {"section": str(tiers["primary"].pk)}
        )
        assert form.is_valid(), form.errors
        effect = form.compile()
        assert str(effect) == "puts the chosen set under Primary (Skills & Powers)"

    def test_the_wrong_collections_section_refuses_in_words(self, skills_and_powers):
        """Reject a section belonging to a different collection during form validation."""
        collection, tiers = skills_and_powers
        archetypes = create_collection("Archetypes")
        pick = section_of(archetypes, "Pick", 0)
        form = generate_form(specs()["ef_places_choice"])(
            {"section": str(pick.pk)}, collection=collection
        )
        assert not form.is_valid()
        assert form.errors["section"] == [
            "That section belongs to Archetypes, not Skills & Powers."
        ]

    def test_the_condition_formset_requires_the_chosen_kinds_fields(self, default_pack):
        formset = condition_formset_for(
            specs()["targets_model"], one_condition("has_subtypes")
        )
        assert not formset.is_valid()
        assert formset.errors[0]["subtypes"] == [
            "A has_subtypes condition needs subtypes."
        ]

    def test_the_type_condition_is_offered_and_compiles(
        self, default_pack, fighter_type
    ):
        formset = condition_formset_for(
            specs()["targets_model"], one_condition("is_profile_type")
        )
        assert not formset.is_valid()
        assert formset.errors[0]["profile_types"] == [
            "A is_profile_type condition needs profile_types."
        ]

        formset = condition_formset_for(
            specs()["targets_model"],
            one_condition("is_profile_type", profile_types=[str(fighter_type.pk)]),
        )
        assert formset.is_valid(), formset.errors


class TestTheUnionPicker:
    def test_picking_an_existing_thing(self, default_pack):
        mounted = create_subtype("Mounted")
        form = generate_form(specs()["ef_adds"])(
            {"thing_kind": "subtype", "thing_subtype": str(mounted.pk)}
        )
        assert form.is_valid(), form.errors
        assert str(form.compile()) == "adds Mounted"

    def test_naming_a_new_rule_creates_it_at_compile(self, default_pack):
        """Inline rule creation retains the shared name-only help text."""
        from n26.library.models import Rule

        form_class = generate_form(specs()["ef_adds"])
        assert form_class().fields["thing_new_rule"].help_text == NAME_ONLY_HELP

        form = form_class(
            {"thing_kind": "rule", "thing_new_rule": "Cult of Personality"}
        )
        assert form.is_valid(), form.errors
        assert not Rule.objects.filter(name="Cult of Personality").exists()
        effect = form.compile()
        assert str(effect) == "adds Cult of Personality"
        assert Rule.objects.filter(name="Cult of Personality").exists()

    def test_a_named_rule_puts_its_bracket_in_the_annotation(self, default_pack):
        """Split a typed annotation from the rule name so inline creation uses the same
        identity as existing rows.
        """
        from n26.library.models import Rule

        form = generate_form(specs()["ef_adds"])(
            {"thing_kind": "rule", "thing_new_rule": 'Leash (3")'}
        )
        assert form.is_valid(), form.errors
        form.compile()

        rule = Rule.objects.get(name="Leash")
        assert rule.annotation == '3"'
        assert str(rule) == 'Leash (3")'

    def test_the_form_and_the_importer_read_a_name_the_same_way(self, default_pack):
        """Forms and ingestion must split names and annotations consistently."""
        from n26.library.authoring import split_annotation
        from n26.library.ingest import _name_and_annotation

        for typed in ('Leash (3")', "Melee", "Ammo (5+)", "Knockback (6+)"):
            assert split_annotation(typed) == _name_and_annotation(typed)

    def test_neither_picked_nor_named_refuses_in_words(self, default_pack):
        form = generate_form(specs()["ef_adds"])({"thing_kind": "rule"})
        assert not form.is_valid()
        assert form.errors["thing_rule"] == ["Pick or name a rule."]

    def test_both_picked_and_named_refuses_in_words(self, default_pack):
        from n26.tests.sandbox.actions import create_rule

        existing = create_rule("Overheat!")
        form = generate_form(specs()["ef_adds"])(
            {
                "thing_kind": "rule",
                "thing_rule": str(existing.pk),
                "thing_new_rule": "Overheats More!",
            }
        )
        assert not form.is_valid()
        assert form.errors["thing_rule"] == [
            "Pick an existing rule or name a new one, not both."
        ]

    def test_the_labels_never_show_the_field_stem(self, default_pack):
        """Union field names include a spec-field prefix; display labels omit it."""
        form = generate_form(specs()["add_built_in"])()
        assert form.fields["thing_kind"].label == "Kind"
        assert form.fields["thing_subtype"].label == "Subtype"
        assert form.fields["thing_wargear"].label == "Wargear"
        assert form.fields["thing_new_subtype"].label == "New subtype"
        # The dropdown labels are readable while values retain kind keys.
        assert ("wargear", "wargear") in form.fields["thing_kind"].choices

    def test_the_picker_never_offers_a_weapon_profile(self, default_pack):
        """Weapon profiles require a parent weapon member and are not standalone union
        choices.
        """
        form = generate_form(specs()["add_built_in"])()
        assert "thing_weapon_profile" not in form.fields
        kinds = [kind for kind, _ in form.fields["thing_kind"].choices]
        assert "weapon_profile" not in kinds

    def test_every_control_says_which_kind_it_belongs_to(self, default_pack):
        """Union controls carry kind markers for selective display."""
        form = generate_form(specs()["add_built_in"])()
        assert "data-union-kind" in str(form["thing_kind"])
        assert 'data-union-member="collection"' in str(form["thing_collection"])
        assert 'data-union-member="wargear"' in str(form["thing_wargear"])
        assert 'data-union-member="rule"' in str(form["thing_new_rule"])


class TestTheComposer:
    def brawler_leader_data(self, leader, combat_category, primary):
        """POST payload for a Leader-scoped Combat-to-Primary placement."""
        return {
            "scope_kind": "targets_model",
            "effect_kind": "ef_places",
            **one_condition("has_subtypes", subtypes=[str(leader.pk)]),
            "what-category": str(combat_category.pk),
            "what-section": str(primary.pk),
        }

    def test_a_valid_submit_is_exactly_the_example_objects_rows(
        self, skills_and_powers
    ):
        """Compile scope, condition and effect rows, attach the modifier and name it from
        carrier plus scope.
        """
        from n26.library.models import HasSubtypes, Modifier

        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_affiliation("Brawler")

        form = ModifierComposerForm(
            self.brawler_leader_data(leader, combat, tiers["primary"]),
            attach_to=brawler,
        )
        assert form.is_valid(), form.errors
        row = form.save()

        assert str(row.scope) == "Outcast Leader models"
        assert str(row.effect) == "puts Combat under Primary (Skills & Powers)"
        assert row.name == (
            "Brawler, Outcast Leader models: "
            "puts Combat under Primary (Skills & Powers)"
        )
        assert list(brawler.modifiers.all()) == [row]
        (condition,) = HasSubtypes.objects.filter(scope=row.scope)
        assert list(condition.subtypes.all()) == [leader]
        assert Modifier.objects.count() == 1

    def test_two_ranks_placing_one_category_are_told_apart(self, skills_and_powers):
        """Include rank conditions in generated names so otherwise identical placements
        remain distinct.
        """
        collection, tiers = skills_and_powers
        combat = create_category("Skills", "Combat")
        brawler = create_affiliation("Brawler")

        written = []
        for rank in ("Outcast Leader", "Outcast Champion"):
            form = ModifierComposerForm(
                self.brawler_leader_data(
                    create_subtype(rank), combat, tiers["primary"]
                ),
                attach_to=brawler,
            )
            assert form.is_valid(), form.errors
            written.append(form.save().name)

        assert written == [
            "Brawler, Outcast Leader models: "
            "puts Combat under Primary (Skills & Powers)",
            "Brawler, Outcast Champion models: "
            "puts Combat under Primary (Skills & Powers)",
        ]

    def test_a_given_name_beats_the_auto_sentence(self, skills_and_powers):
        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_affiliation("Brawler")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        data["name"] = "Brawler leader: combat primary"
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        assert form.save().name == "Brawler leader: combat primary"

    def test_incompatible_who_and_what_is_a_form_error_in_words(self, default_pack):
        """Reject a trait effect aimed at a model before saving any rows."""
        from n26.library.models import Modifier, TargetsMiniature

        backstab = create_trait("Backstab")
        form = ModifierComposerForm(
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_adds",
                **no_conditions(),
                "what-thing_kind": "trait",
                "what-thing_trait": str(backstab.pk),
            }
        )
        assert not form.is_valid()
        (error,) = form.non_field_errors()
        assert "cannot apply" in error
        assert Modifier.objects.count() == 0
        assert TargetsMiniature.objects.count() == 0

    def test_make_reusable_names_it_generically_and_attaches_anyway(
        self, skills_and_powers
    ):
        """Reusable naming omits the carrier while retaining attachment to the current
        carrier.
        """
        from n26.library.authoring import attach_modifiers_to

        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_affiliation("Brawler")
        crusher = create_affiliation("Bone Crusher")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        data["make_reusable"] = "on"
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        row = form.save()

        assert list(brawler.modifiers.all()) == [row]
        assert "Brawler" not in row.name
        # The same modifier can attach to another carrier.
        attach_modifiers_to(crusher, [row])
        assert list(crusher.modifiers.all()) == [row]

    def test_without_it_the_carrier_leads_the_name(self, skills_and_powers):
        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_affiliation("Brawler")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        row = form.save()

        assert list(brawler.modifiers.all()) == [row]
        # Scope conditions distinguish generated names for otherwise equal placements.
        assert row.name.startswith("Brawler, Outcast Leader models: ")

    def test_pane_errors_surface_on_the_composer(self, default_pack):
        """Missing effect fields appear as composer errors."""
        form = ModifierComposerForm(
            {
                "scope_kind": "targets_model",
                "effect_kind": "ef_places",
                **no_conditions(),
                # what-category and what-section both missing
            }
        )
        assert not form.is_valid()
        assert any("what category" in error for error in form.non_field_errors())


class TestEverySpecGeneratesAForm:
    """Every registered spec must produce an instantiable form with valid fields."""

    @pytest.mark.parametrize("name", sorted(specs()), ids=str)
    def test_the_form_class_builds_and_instantiates(self, name):
        form = generate_form(specs()[name])()
        signature = inspect.signature(specs()[name].verb)
        # Every flat form field is a real verb parameter or a union part.
        for field_name in form.fields:
            root = field_name.split("_")[0] if "_" in field_name else field_name
            assert (
                field_name in signature.parameters
                or any(field_name.startswith(f"{p}_") for p in signature.parameters)
                or root in signature.parameters
            )

    @pytest.mark.parametrize("name", sorted(specs()), ids=str)
    def test_every_sourced_text_field_carries_its_columns_limit(self, name):
        """Use the source model’s max_length so overlong values fail form validation before
        database insertion.
        """
        from n26.library.specs import Text

        spec = specs()[name]
        form = generate_form(spec)()
        for field_name, kind in spec.fields.items():
            if not isinstance(kind, Text) or kind.source is None:
                continue
            model, column = kind.source
            expected = getattr(model._meta.get_field(column), "max_length", None)
            assert form.fields[field_name].max_length == expected, (
                f"{name}.{field_name}: form allows what {model.__name__}."
                f"{column} refuses"
            )

    def test_an_overlong_qualifier_is_words_not_a_500(self):
        """Overlong qualifiers redisplay as field errors."""
        form = generate_form(specs()["add_weapon_profile"])(
            data={"name": "hotshot", "price": "5", "qualifier": "q" * 101}
        )
        assert not form.is_valid()
        assert "qualifier" in form.errors


class TestALongConditionStillComposes:
    """Summarise large conditions so generated names fit their model column."""

    def test_many_profiles_summarise_rather_than_enumerate(self, db, default_pack):
        from n26.library.authoring import (
            create_gang_type,
            create_profile,
            create_profile_type,
            create_stat,
            create_statline_type,
            is_profile,
            targets_model,
        )

        statline_type = create_statline_type("Bare", stats=[create_stat("M", "Move")])
        kind = create_profile_type("Fighter", statline_type)
        home = create_gang_type("Crowded")
        profiles = [
            create_profile(f"A Very Long Profile Name Indeed Number {n}", kind, home)
            for n in range(8)
        ]
        scope = targets_model(is_profile(*profiles))
        said = str(scope)
        assert "or 6 more" in said
        assert len(said) < 200

    def test_a_typed_name_too_long_is_a_form_error_not_a_broken_page(self):
        from n26.library.forms import ModifierComposerForm

        assert ModifierComposerForm.base_fields["name"].max_length == 200
