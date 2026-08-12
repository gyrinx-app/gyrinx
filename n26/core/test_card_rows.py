"""The card-row declarations, held together.

A kind declares where its lines go — ``card_row`` on the library model —
and three other places must agree: the ModelCard carries a list field per
declared row, the ComputedCard files grants into a bucket of the same
name, and the card template draws a Choose control for every row that
takes questions. Nothing structural connects them, so this does: the
kinds are discovered, never listed, and a new declaration that misses a
step fails here with the step named.
"""

import dataclasses
from pathlib import Path

from django.apps import apps

import n26.core
from n26.core.effects import ComputedCard
from n26.core.render import ModelCard
from n26.library.models.assignable import Assignable

CARD_TEMPLATE = (
    Path(n26.core.__file__).parent / "templates/cotton/n26/model_card/index.html"
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
            assert row in on_computed, (
                f"A kind declares card_row={row!r} but ComputedCard has no "
                f"{row!r} bucket (n26/core/effects.py). A modifier granting "
                f"one of these would be filed nowhere."
            )

    def test_every_question_row_is_real_and_drawn(self):
        template = CARD_TEMPLATE.read_text()
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
            assert f"card.{bucket}" in template, (
                f"The card template never draws card.{bucket} — a question "
                f"routed to the {row!r} row would silently vanish from the "
                f"card. Give the row the Choose treatment the Skills row has."
            )
