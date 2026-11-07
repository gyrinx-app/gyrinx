"""Attachment asks and suggested built-ins come from model declarations. These tests
validate those declarations and the forms derived from their resolved offers.
"""

import pytest

from n26.library.forms import generate_form, suggestion_form_for
from n26.library.offers import attachment_asks, attachment_contexts, built_in_offer
from n26.library.specs import specs

pytestmark = pytest.mark.django_db


def library_assignables():
    """Discover every concrete Assignable model."""
    from django.apps import apps

    from n26.library.models.assignable import Assignable

    return [
        model
        for model in apps.get_app_config("library").get_models()
        if issubclass(model, Assignable)
    ]


def chosen_only_kinds():
    """Kinds whose declarations prohibit built-ins."""
    return [model for model in library_assignables() if not model.takes_built_ins]


def a_row_of(model, name):
    """Create a minimal row and its required related rows by reflection, so newly
    discovered kinds remain covered. Fields with defaults retain them.
    """
    required = {
        field.name: a_row_of(field.related_model, f"{name} {field.name}")
        for field in model._meta.fields
        if field.many_to_one and not field.null and not field.has_default()
    }
    return model.objects.create(**{_naming_field(model): name}, **required)


def _naming_field(model):
    """Use name when present, otherwise the first required text field."""
    names = {field.name for field in model._meta.fields}
    if "name" in names:
        return "name"
    return next(
        field.name
        for field in model._meta.fields
        if field.get_internal_type() == "CharField" and not field.blank
    )


def acquired_kind_pages():
    """Authoring pages for kinds that allow built-ins."""
    from n26.library.views import _kind_slugs

    slugs = _kind_slugs()
    return [
        slugs[model]
        for model in library_assignables()
        if model.takes_built_ins and model in slugs
    ]


class TestTheDeclarationsHoldTogether:
    """Declarations must use valid contexts and fields available on their through model."""

    def test_there_is_something_to_check(self):
        assert len(library_assignables()) > 10

    @pytest.mark.parametrize("model", library_assignables(), ids=lambda m: m.__name__)
    def test_every_declared_ask_names_a_real_context_and_column(self, model):
        contexts = attachment_contexts()
        for context, field_names in model.ATTACHMENT_ASKS.items():
            assert context in contexts, (
                f"{model.__name__} declares asks for {context!r}, which no "
                f"through row calls itself. Known: {sorted(contexts)}."
            )
            for field_name in field_names:
                contexts[context]._meta.get_field(field_name)

    @pytest.mark.parametrize("model", library_assignables(), ids=lambda m: m.__name__)
    def test_every_suggestion_is_a_kind_built_ins_can_name(self, model):
        """Every suggested kind must be representable by DefaultAssignment and resolve to a
        valid offer.
        """
        from n26.library.offers import Suggest, _built_in_key

        for suggest in getattr(model, "SUGGESTED_BUILT_INS", ()):
            assert isinstance(suggest, Suggest)
            assert suggest.label
            _built_in_key(suggest.kind)  # raises if built-ins cannot name it
        built_in_offer(model)  # raises on named+many or many+asks


class TestAttachmentAsks:
    def test_a_counter_built_in_asks_for_its_opening_value(self):
        from n26.library.models import Counter, DefaultAssignment

        (ask,) = attachment_asks(Counter, DefaultAssignment)
        assert ask.name == "amount"
        assert ask.input == "number"
        # Help comes from the through-model field.
        assert ask.help == str(DefaultAssignment._meta.get_field("amount").help_text)

    def test_a_collection_built_in_asks_for_nothing(self):
        from n26.library.models import Collection, DefaultAssignment

        assert attachment_asks(Collection, DefaultAssignment) == ()

    def test_a_collection_entry_asks_for_its_price_overrides(self):
        """Purchasable collection entries expose price overrides."""
        from n26.library.models import CollectionEntry, Weapon

        names = [ask.name for ask in attachment_asks(Weapon, CollectionEntry)]
        assert names == ["price_override", "trade_point_override"]


class TestTheBuiltInOffer:
    def test_a_kind_that_suggests_nothing_offers_nothing(self):
        from n26.library.models import Wargear

        assert built_in_offer(Wargear) == ()

    def test_the_profiles_offer_resolved_against_the_library(self, default_pack):
        from n26.library.authoring import (
            create_collection,
            create_counter,
            create_subtype,
        )
        from n26.library.models import Profile

        xp = create_counter("XP")
        escher_list = create_collection("House Escher Equipment List")
        ganger = create_subtype("Ganger")

        starting_xp, equipment, subtype = built_in_offer(Profile)

        assert starting_xp.label == "Starting XP"
        assert starting_xp.kind == "counter"
        assert starting_xp.fixed == xp
        assert starting_xp.candidates == ()
        assert [ask.name for ask in starting_xp.asks] == ["amount"]

        assert equipment.label == "Equipment list"
        assert equipment.kind == "collection"
        assert equipment.fixed is None
        assert equipment.candidates == (escher_list,)
        assert equipment.asks == ()

        assert subtype.label == "Subtypes"
        assert subtype.kind == "subtype"
        assert subtype.candidates == (ganger,)
        assert subtype.many is True
        assert (starting_xp.many, equipment.many) == (False, False)

    def test_a_missing_named_row_falls_back_to_candidates(self, default_pack):
        """Without the named XP counter, the offer falls back to available counters."""
        from n26.library.authoring import create_counter
        from n26.library.models import Profile

        kills = create_counter("Kill Count")
        starting_xp, *_ = built_in_offer(Profile)
        assert starting_xp.fixed is None
        assert starting_xp.candidates == (kills,)

    def test_a_kind_built_ins_cannot_name_refuses_loudly(self):
        from n26.library.models import GangType
        from n26.library.offers import _built_in_key

        with pytest.raises(ValueError, match="cannot be a built-in"):
            _built_in_key(GangType)

    def test_many_contradicts_a_named_row_and_asks(self, default_pack):
        """Multi-select offers cannot name a single row or collect per-pick attachment
        values.
        """
        from n26.library.models import Counter, Subtype
        from n26.library.offers import Suggest

        class NamedAndMany:
            SUGGESTED_BUILT_INS = (
                Suggest("Subtypes", Subtype, named="Ganger", many=True),
            )

        class ManyWithAsks:
            SUGGESTED_BUILT_INS = (Suggest("Counters", Counter, many=True),)

        with pytest.raises(ValueError, match="many"):
            built_in_offer(NamedAndMany)
        with pytest.raises(ValueError, match="many"):
            built_in_offer(ManyWithAsks)

    def test_the_slug_is_the_label_as_a_field_stem(self, default_pack):
        from n26.library.models import Profile

        starting_xp, equipment, _ = built_in_offer(Profile)
        assert starting_xp.slug == "starting_xp"
        assert equipment.slug == "equipment_list"


class TestTheUnionCarriesTheAsks:
    """The amount field applies only when the selected kind is Counter."""

    def form(self, data=None):
        return generate_form(specs()["add_built_in"])(data)

    def test_the_ask_rides_the_form_marked_with_its_kind(self, default_pack):
        rendered = str(self.form()["amount"])
        assert 'data-union-member="counter"' in rendered
        assert 'data-union-of="thing"' in rendered

    def test_the_asks_help_is_the_through_rows_words(self, default_pack):
        from n26.library.models import DefaultAssignment

        assert self.form().fields["amount"].help_text == str(
            DefaultAssignment._meta.get_field("amount").help_text
        )

    def test_the_chosen_kinds_ask_reaches_the_verb(self, default_pack):
        from n26.library.authoring import create_counter

        xp = create_counter("XP")
        form = self.form(
            {"thing_kind": "counter", "thing_counter": str(xp.pk), "amount": "61"}
        )
        assert form.is_valid(), form.errors
        assert form.verb_data() == {"thing": xp, "amount": 61}

    def test_another_kinds_ask_is_dropped_not_passed(self, default_pack):
        """Changing the selected kind discards attachment values belonging to the previous
        kind.
        """
        from n26.library.authoring import create_collection

        post = create_collection("Trading Post")
        form = self.form(
            {
                "thing_kind": "collection",
                "thing_collection": str(post.pk),
                "amount": "61",
            }
        )
        assert form.is_valid(), form.errors
        assert form.verb_data() == {"thing": post}


class TestTheSuggestionForm:
    def test_a_kind_without_suggestions_has_no_form(self):
        from n26.library.models import Wargear

        assert suggestion_form_for(Wargear) is None

    def test_blank_everywhere_builds_nothing_in(self, default_pack, make_profile):
        from n26.library.authoring import create_collection, create_counter
        from n26.library.models import Profile

        create_counter("XP")
        create_collection("House Escher Equipment List")
        form = suggestion_form_for(Profile)({})
        assert form.is_valid(), form.errors

        ganger = make_profile("Ganger")
        assert form.apply(ganger) == []
        assert not ganger.built_in_members.exists()

    def test_taking_both_suggestions(self, default_pack, make_profile):
        from n26.library.authoring import create_collection, create_counter
        from n26.library.models import Profile

        xp = create_counter("XP")
        escher_list = create_collection("House Escher Equipment List")
        form = suggestion_form_for(Profile)(
            {"starting_xp_amount": "61", "equipment_list": str(escher_list.pk)}
        )
        assert form.is_valid(), form.errors

        ganger = make_profile("Ganger")
        made = form.apply(ganger)

        assert [member.assignable for member in made] == [xp, escher_list]
        ganger.refresh_from_db()
        by_thing = {m.assignable: m for m in ganger.built_in_members}
        assert by_thing[xp].amount == 61

    def test_an_unofferable_suggestion_is_left_out(self, default_pack):
        """An empty counter collection omits the Starting XP suggestion."""
        from n26.library.authoring import create_collection
        from n26.library.models import Profile

        create_collection("House Escher Equipment List")
        form = suggestion_form_for(Profile)()
        assert "starting_xp_amount" not in form.fields
        assert "equipment_list" in form.fields

    def test_a_many_suggestion_takes_several_picks(self, default_pack, make_profile):
        """Each selected subtype becomes a built-in."""
        from n26.library.authoring import create_subtype
        from n26.library.models import Profile

        ganger = create_subtype("Ganger")
        specialist = create_subtype("Specialist")
        form = suggestion_form_for(Profile)(
            {"subtypes": [str(ganger.pk), str(specialist.pk)]}
        )
        assert form.is_valid(), form.errors

        yolanda = make_profile("Yolanda")
        made = form.apply(yolanda)

        assert {member.assignable for member in made} == {ganger, specialist}
        yolanda.refresh_from_db()
        assert yolanda.built_in_members.count() == 2


class TestTheKindsOnlyEverChosen:
    """Chosen-only kinds receive modifiers rather than built-ins. Their pages omit the
    built-in section, and the authoring verb rejects attachments.
    """

    def test_there_is_something_to_check(self):
        named = {model.__name__ for model in chosen_only_kinds()}
        assert {"Affiliation", "Pickable"} <= named
        assert len(acquired_kind_pages()) > 5

    @pytest.mark.parametrize(
        "model", chosen_only_kinds(), ids=lambda model: model.__name__
    )
    def test_its_page_offers_no_built_ins(self, model):
        from n26.library.views import _carries_built_ins, _kind_slugs

        assert not _carries_built_ins(_kind_slugs()[model])

    @pytest.mark.parametrize(
        "model", chosen_only_kinds(), ids=lambda model: model.__name__
    )
    def test_the_verb_refuses_to_build_anything_into_one(self, model, default_pack):
        """The authoring verb enforces the same restriction for importers."""
        from django.core.exceptions import ValidationError

        from n26.library.authoring import add_built_in, create_rule

        chosen = a_row_of(model, f"Something {model.__name__}")
        brought = create_rule(f"What a {model.__name__} brings")

        with pytest.raises(ValidationError, match="chosen rather than acquired"):
            add_built_in(chosen, brought)

        chosen.refresh_from_db()
        assert chosen.built_ins_id is None

    @pytest.mark.parametrize(
        "model", chosen_only_kinds(), ids=lambda model: model.__name__
    )
    def test_it_suggests_nothing_at_create(self, model):
        from n26.library.forms import suggestion_form_for

        assert built_in_offer(model) == ()
        assert suggestion_form_for(model) is None

    def test_a_kind_that_says_both_things_refuses_loudly(self):
        """A kind cannot prohibit built-ins while suggesting them on its create page."""
        from n26.library.models import Counter
        from n26.library.offers import Suggest

        class ChosenButSuggesting:
            takes_built_ins = False
            SUGGESTED_BUILT_INS = (Suggest("Starting XP", Counter, named="XP"),)

        with pytest.raises(ValueError, match="takes no built-ins"):
            built_in_offer(ChosenButSuggesting)

    def test_the_page_of_a_chosen_thing_draws_no_comes_with_form(
        self, client, default_pack
    ):
        """Affiliation pages omit built-ins; wargear pages retain them."""
        from django.contrib.auth.models import User
        from django.urls import reverse

        from n26.library.authoring import create_affiliation, create_wargear

        client.force_login(User.objects.create_user("author", is_staff=True))
        chosen = create_affiliation("Chaos Corrupted")
        bought = create_wargear("Cyber-mastiff")

        def page(kind, thing):
            return client.get(
                reverse("authoring-detail", kwargs={"kind": kind, "pk": thing.pk})
            ).content.decode()

        asked = "the moment it is acquired"
        assert asked not in page("affiliation", chosen)
        assert asked in page("wargear", bought)

    @pytest.mark.parametrize("kind", acquired_kind_pages())
    def test_every_page_of_something_acquired_still_offers_them(self, kind):
        from n26.library.views import _carries_built_ins

        assert _carries_built_ins(kind)

    def test_the_verb_still_builds_into_something_bought(self, default_pack):
        from n26.library.authoring import add_built_in, create_rule, create_wargear

        mastiff = create_wargear("Cyber-mastiff")
        rule = create_rule("Guard")
        add_built_in(mastiff, rule)

        mastiff.refresh_from_db()
        assert [member.assignable for member in mastiff.built_in_members] == [rule]
