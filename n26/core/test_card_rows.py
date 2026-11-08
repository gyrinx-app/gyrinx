"""Discover card-row declarations and check their rendering and choice-routing
connections.

ModelCard and ComputedCard need matching fields for each declared card row. Choice
buckets also need template controls and picker links.
"""

import dataclasses
from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from django.template import Context, Template
from django.template.loader import render_to_string
from django_cotton.compiler_regex import CottonCompiler

import n26.core
from n26.core import render as render_module
from n26.core.effects import ComputedCard
from n26.core.render import ModelCard
from n26.library.models.assignable import Assignable

#: Choice markup may be in either the card frame or its body include.
CARD_TEMPLATES = (
    Path(n26.core.__file__).parent / "templates/cotton/n26/model_card/index.html",
    Path(n26.core.__file__).parent / "templates/cotton/n26/model_card/body.html",
)


def declared_rows():
    return {
        model.card_row
        for model in apps.get_app_config("library").get_models()
        if issubclass(model, Assignable) and model.card_row is not None
    }


class TestTheCardRows:
    def test_there_is_something_to_check(self):
        assert "skills" in declared_rows()

    def test_every_declared_row_is_a_field_on_both_structures(self):
        on_card = {f.name for f in dataclasses.fields(ModelCard)}
        on_computed = {f.name for f in dataclasses.fields(ComputedCard)}
        for row in sorted(declared_rows()):
            assert row in on_card, (
                f"A kind declares card_row={row!r} but ModelCard has no "
                f"{row!r} list field. Add the field (n26/core/render.py) and "
                f"wire it into card_to_model_card's line_rows mapping, or "
                f"the kind's lines have nowhere to land."
            )
            definition = next(f for f in dataclasses.fields(ModelCard) if f.name == row)
            assert definition.metadata.get("row_label") or definition.metadata.get(
                "row_elsewhere"
            ), (
                f"ModelCard.{row} needs row_label metadata for the shared row composer, "
                "or a row_elsewhere reason naming its other presentation."
            )
            assert row in on_computed, (
                f"A kind declares card_row={row!r} but ComputedCard has no "
                f"{row!r} bucket (n26/core/effects.py). A modifier granting "
                f"one of these would be filed nowhere."
            )

    def test_every_question_row_is_real_and_drawn(self):
        rows = declared_rows()
        on_card = {f.name for f in dataclasses.fields(ModelCard)}
        for row, bucket in ModelCard.QUESTION_BUCKETS.items():
            assert row in rows, (
                f"QUESTION_BUCKETS names {row!r} but no kind declares that "
                f"card_row — a question routed there would join a row no "
                f"line can ever be in."
            )
            assert bucket in on_card, (
                f"QUESTION_BUCKETS routes {row!r} questions into "
                f"ModelCard.{bucket}, which does not exist."
            )
            definition = next(f for f in dataclasses.fields(ModelCard) if f.name == row)
            assert definition.metadata.get("row_label"), (
                f"ModelCard.{row} needs row_label metadata so its facts and questions "
                "reach the shared composer and all card renderers."
            )
            from n26.core.printing import detail_groups
            from n26.core.render import ChoiceLine, Statline
            from n26.core.render_text import render_model_card

            choice = ChoiceLine(row, None, href=f"/choose/{row}/")
            card = ModelCard("Nobody", 0, Statline(), **{bucket: [choice]})
            assert any(
                part.value is choice
                for detail in card.detail_rows
                for part in detail.parts
            )
            html = Template(
                CottonCompiler().process(
                    '<c-n26.model-card.body :card="card" mode="edit" />'
                )
            ).render(Context({"card": card}))
            assert choice.href in html, f"The {row} question has no visible picker."
            label = definition.metadata["row_label"]
            assert any(
                group.label == label and "—" in group.text
                for group in detail_groups(card)
            )
            assert any(
                f"{label}: {row}: — (not chosen)" in line
                for line in render_model_card(card)
            )

    def test_a_question_a_weapon_carries_is_linked_and_drawn(self):
        """Item choices render under their item, outside row-level buckets, and still
        require picker links.
        """
        from n26.core.render import ChoiceLine, Statline, WeaponLine
        from n26.core.views.choose import link_slots

        card = ModelCard(
            name="Nobody",
            rating=0,
            statline=Statline(),
            weapons=[
                WeaponLine(
                    name="Gun",
                    base_rating=0,
                    choices=[
                        ChoiceLine(kind_label="Augmentation", chosen=None, key="a:b:1")
                    ],
                )
            ],
        )
        assert card.questions == card.weapons[0].choices
        assert card.row_questions == []
        link_slots(SimpleNamespace(pk="a-gang"), card)
        assert card.weapons[0].choices[0].href
        template = "".join(t.read_text() for t in CARD_TEMPLATES)
        name_template = (
            Path(n26.core.__file__).parent / "templates/n26/includes/weapon_name.html"
        ).read_text()
        assert "weapon.other_choice_rows" in template
        assert "weapon.choices" in name_template

    def test_a_non_tier_gear_choice_stays_visible_on_the_roster(self):
        from bs4 import BeautifulSoup

        from n26.core.render import AssignableLine, ChoiceLine

        line = AssignableLine(
            name="Banner",
            choices=[
                ChoiceLine(
                    kind_label="Legacy",
                    chosen=None,
                    href="/choose/",
                    dismiss_href="/dismiss/",
                    back="/gang/",
                )
            ],
        )
        roster = BeautifulSoup(
            render_to_string(
                "n26/includes/gear_lines.html",
                {"lines": [line], "has_actions": True, "mode": "gang"},
            ),
            "html.parser",
        )
        assert "Banner — Legacy: —" in roster.get_text(" ", strip=True)
        assert roster.find("form", action="/dismiss/")

        edit = BeautifulSoup(
            render_to_string(
                "n26/includes/gear_lines.html",
                {"lines": [line], "has_actions": True, "mode": "edit"},
            ),
            "html.parser",
        )
        assert edit.find("a", href="/choose/").get_text(" ", strip=True) == "Choose"

    def test_every_question_row_is_pointed_at_its_picker(self):
        """Every rendered choice control needs a URL, including choices in newly
        declared buckets.
        """
        from n26.core.render import ChoiceLine, Statline
        from n26.core.views.choose import link_slots

        for row, bucket in ModelCard.QUESTION_BUCKETS.items():
            card = ModelCard(
                name="Nobody",
                rating=0,
                statline=Statline(),
                **{bucket: [ChoiceLine(kind_label=row, chosen=None, key="a:b:1")]},
            )
            link_slots(SimpleNamespace(pk="a-gang"), card)
            (line,) = getattr(card, bucket)
            assert line.href, (
                f"Nothing points ModelCard.{bucket} at its picker, so a "
                f"question in the {row!r} row draws a control that goes "
                f"nowhere. link_slots (n26/core/views/choose.py) should ask "
                f"the holder for every question it has — ModelCard.questions "
                f"— rather than name one list at a time."
            )


def choice_holders():
    return [
        cls
        for cls in vars(render_module).values()
        if isinstance(cls, type)
        and dataclasses.is_dataclass(cls)
        and cls.__module__ == render_module.__name__
        and any("ChoiceLine" in str(field.type) for field in dataclasses.fields(cls))
    ]


class TestEveryChoiceProducer:
    def test_there_are_choice_bearing_structures_to_check(self):
        assert ModelCard in choice_holders()

    def test_every_choice_field_is_projected_or_has_an_explicit_hidden_reason(self):
        from n26.core.render import ChoiceLine

        for cls in choice_holders():
            for source in dataclasses.fields(cls):
                if "ChoiceLine" not in str(source.type):
                    continue
                if source.metadata.get("row_hidden"):
                    continue
                # Render structures are plain data; initialise their defaults so
                # each source is checked alone, including frozen item structures.
                holder = object.__new__(cls)
                for field in dataclasses.fields(cls):
                    if field.default_factory is not dataclasses.MISSING:
                        value = field.default_factory()
                    elif field.default is not dataclasses.MISSING:
                        value = field.default
                    else:
                        value = "owner" if field.type is str else None
                    object.__setattr__(holder, field.name, value)
                choice = ChoiceLine("Guard heading", None, key="guard")
                object.__setattr__(holder, source.name, [choice])
                rows = [
                    row
                    for name in (
                        "detail_rows",
                        "other_choice_rows",
                        "owned_choice_rows",
                    )
                    for row in getattr(holder, name, ())
                ]
                assert any(
                    part.value is choice for row in rows for part in row.parts
                ), (
                    f"{cls.__name__}.{source.name} bypasses the row composer. "
                    "Project this source, or declare a row_hidden reason if it is not a visible fact."
                )
