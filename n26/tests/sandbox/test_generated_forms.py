"""Spec-generated forms and the modifier composer.

Step 2 of design/authoring-build-plan.md. The tests hold the form layer
to the same standard as the specs beneath it:

* a valid composer submit produces **exactly the example object's
  rows** — "Brawler leader: combat primary", all three, auto-named for
  the carrier they were composed on;
* refusals are **words at form level**: a section of the wrong
  collection, an effect that cannot apply to a scope — never a
  database constraint error after rows exist;
* ``make_reusable`` decides what an unnamed modifier is called, and
  ``attach_modifiers_to`` hangs it on carriers later;
* the union picker creates name-only leaves inline, with the copyright
  guardrail as its help.

Form data everywhere is what a real POST would carry — prefixed panes
(``who-``, ``what-``), a management-formed ``conditions-`` formset —
because the preview endpoint (step 3) will take exactly this shape.
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
    create_archetype,
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
    """The form layer's two lookup tables, checked against the model
    layer and the registry they mirror — never trusted."""

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

    def test_no_two_kind_choices_read_alike(self):
        """Labels default to the model's verbose name, and two verbs may
        write one model — so without a stated label the picker shows one
        choice twice, and an author cannot tell which row carries which
        fields. A verb that collides must state its own label on its
        spec."""
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
        """The plan's example error, verbatim in shape: the section
        belongs to another collection than the one being worked in."""
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


class TestTheUnionPicker:
    def test_picking_an_existing_thing(self, default_pack):
        mounted = create_subtype("Mounted")
        form = generate_form(specs()["ef_adds"])(
            {"thing_kind": "subtype", "thing_subtype": str(mounted.pk)}
        )
        assert form.is_valid(), form.errors
        assert str(form.compile()) == "adds Mounted"

    def test_naming_a_new_rule_creates_it_at_compile(self, default_pack):
        """The create-inline, with the copyright guardrail as its help."""
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
        """A rule's annotation is part of its identity, so a bracket the
        author typed must land there. Otherwise this makes a rule *named*
        "Leash (3")" that prints exactly like the real one, matches
        nothing, and quietly doubles it."""
        from n26.library.models import Rule

        form = generate_form(specs()["ef_adds"])(
            {"thing_kind": "rule", "thing_new_rule": 'Leash (3")'}
        )
        assert form.is_valid(), form.errors
        form.compile()

        rule = Rule.objects.get(name="Leash")
        assert rule.annotation == '3"'
        assert str(rule) == 'Leash (3")'  # prints as the book writes it

    def test_the_form_and_the_importer_read_a_name_the_same_way(self, default_pack):
        """The two writers of content must agree, or each makes rows the
        other cannot find."""
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
        """The names carry the spec field's stem so several unions can
        share a form; the words never do — Django's generated labels
        would read "Thing new subtype"."""
        form = generate_form(specs()["add_built_in"])()
        assert form.fields["thing_kind"].label == "Kind"
        assert form.fields["thing_subtype"].label == "Subtype"
        assert form.fields["thing_weapon_profile"].label == "Weapon profile"
        assert form.fields["thing_new_subtype"].label == "New subtype"
        # The kind dropdown speaks the same way, keeping raw values.
        assert ("weapon_profile", "weapon profile") in form.fields["thing_kind"].choices

    def test_every_control_says_which_kind_it_belongs_to(self, default_pack):
        """The markers base.html's script reads to show only the chosen
        kind's picker. Hints, not structure: strip the script and every
        control shows, and the form still works."""
        form = generate_form(specs()["add_built_in"])()
        assert "data-union-kind" in str(form["thing_kind"])
        assert 'data-union-member="collection"' in str(form["thing_collection"])
        assert 'data-union-member="weapon_profile"' in str(form["thing_weapon_profile"])
        assert 'data-union-member="rule"' in str(form["thing_new_rule"])


class TestTheComposer:
    def brawler_leader_data(self, leader, combat_category, primary):
        """The submit that is the plan's worked example."""
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
        """Brawler leader: combat primary — WHO, WHAT and glue, one
        submit. Composed on a carrier and not marked reusable, so the
        carrier leads the auto-name; the scope narrows to one rank, so
        that rank stays in it and the sentence follows both."""
        from n26.library.models import HasSubtypes, Modifier

        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_archetype("Brawler")

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
        """A grid hangs a row per rank off one archetype, and ranks share
        cells — both of these put Combat under Primary. What the scope
        narrows to is the only thing between the two rows, so it stays in
        the name. Drop it and they are both called the same thing, and
        the second is refused by the unique-name constraint rather than
        merely reading oddly.
        """
        collection, tiers = skills_and_powers
        combat = create_category("Skills", "Combat")
        brawler = create_archetype("Brawler")

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
        brawler = create_archetype("Brawler")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        data["name"] = "Brawler leader: combat primary"
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        assert form.save().name == "Brawler leader: combat primary"

    def test_incompatible_who_and_what_is_a_form_error_in_words(self, default_pack):
        """A trait aimed at a model — the models' own refusal, surfaced
        before any row exists."""
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
        assert TargetsMiniature.objects.count() == 0  # nothing written

    def test_make_reusable_names_it_generically_and_attaches_anyway(
        self, skills_and_powers
    ):
        """Reusable is a claim about the name, not about where the row
        goes. It attaches to the carrier it was composed on like any
        other, and is named for what it does so it still reads true on
        the next carrier it is given to."""
        from n26.library.authoring import attach_modifiers_to

        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_archetype("Brawler")
        crusher = create_archetype("Bone Crusher")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        data["make_reusable"] = "on"
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        row = form.save()

        assert list(brawler.modifiers.all()) == [row]
        assert "Brawler" not in row.name
        # And it still goes on as many others as an author wants.
        attach_modifiers_to(crusher, [row])
        assert list(crusher.modifiers.all()) == [row]

    def test_without_it_the_carrier_leads_the_name(self, skills_and_powers):
        collection, tiers = skills_and_powers
        leader = create_subtype("Outcast Leader")
        combat = create_category("Skills", "Combat")
        brawler = create_archetype("Brawler")

        data = self.brawler_leader_data(leader, combat, tiers["primary"])
        form = ModifierComposerForm(data, attach_to=brawler)
        assert form.is_valid(), form.errors
        row = form.save()

        assert list(brawler.modifiers.all()) == [row]
        # The carrier leads. What the scope narrows to follows it, being
        # the only thing between this row and the same placement made for
        # another rank.
        assert row.name.startswith("Brawler, Outcast Leader models: ")

    def test_pane_errors_surface_on_the_composer(self, default_pack):
        """A missing WHAT field is said as words on the one form the
        admin is looking at."""
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
    """The step's own discovering sweep: no spec may be form-hostile."""

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
