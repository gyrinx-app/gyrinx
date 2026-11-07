"""Heading composition preserves independent values, addresses and display owners."""

import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.printing import detail_groups
from n26.core.render import (
    AssignableLine,
    ChoiceLine,
    CounterLine,
    GangSheet,
    GearGroup,
    ModelCard,
    Statline,
    WeaponLine,
    hide_dismissed,
)
from n26.core.render_text import render_gang_sheet, render_model_card
from n26.core.rows import (
    Contribution,
    PartKind,
    RowPart,
    Separation,
    compose_rows,
    row_text,
)


def card_with(**kwargs):
    return ModelCard(name="Scout", rating=80, statline=Statline(), **kwargs)


def card_html(card, mode="edit"):
    return BeautifulSoup(
        Template(
            CottonCompiler().process(
                '<c-n26.model-card.body :card="card" mode="{{ mode }}" />'
            )
        ).render(Context({"card": card, "mode": mode})),
        "html.parser",
    )


class TestHeadingComposition:
    def test_equal_headings_combine_without_discarding_duplicate_values_or_controls(
        self,
    ):
        choices = [
            ChoiceLine(
                "  Legendary   name ", "One Shot", key="battle", href="/battle/"
            ),
            ChoiceLine("legendary name", "One Shot", key="rank", href="/rank/"),
            ChoiceLine("LEGENDARY NAME", None, key="recruit", href="/recruit/"),
        ]
        card = card_with(choices=choices)
        row = next(row for row in card.detail_rows if row.label == "Legendary name")
        assert [part.value for part in row.parts] == choices
        assert [part.value.key for part in row.parts] == ["battle", "rank", "recruit"]
        assert [part.value.href for part in row.parts] == [
            "/battle/",
            "/rank/",
            "/recruit/",
        ]
        assert row_text(row) == "One Shot, One Shot, —"
        html = card_html(card)
        assert (
            len(
                [
                    dt
                    for dt in html.select("dt")
                    if dt.get_text(strip=True) == "Legendary name"
                ]
            )
            == 1
        )
        assert all(html.find("a", href=choice.href) for choice in choices)
        assert [(group.label, group.text) for group in detail_groups(card)] == [
            ("Legendary name", "One Shot, One Shot, —")
        ]
        assert "Legendary name: One Shot, One Shot, — (not chosen)" in "\n".join(
            render_model_card(card)
        )

    def test_arbitrary_choice_labels_join_ordinary_rows_and_keep_typed_members(self):
        counter = CounterLine(name="Rules", value=7)
        rule = AssignableLine(name="Fast")
        choice = ChoiceLine(" rules ", "Fearless", href="/choose/")
        card = card_with(counters=[counter], rules=[rule], choices=[choice])
        rows = [row for row in card.detail_rows if row.label == "Rules"]
        assert len(rows) == 1
        assert [part.kind for part in rows[0].parts] == [
            PartKind.COUNTER,
            PartKind.NAMES,
            PartKind.CHOICE,
        ]
        assert row_text(rows[0]) == "7, Fast, Fearless"
        html = card_html(card)
        assert (
            len([dt for dt in html.select("dt") if dt.get_text(strip=True) == "Rules"])
            == 1
        )
        assert "Fast" in html.get_text()
        assert html.find("a", href="/choose/")

    def test_headings_do_not_use_fuzzy_plural_matching(self):
        card = card_with(
            choices=[ChoiceLine("Name", "Ash"), ChoiceLine("Names", "Birch")]
        )
        assert [row.label for row in card.detail_rows][-2:] == ["Name", "Names"]

    def test_projection_reads_linking_and_dismissal_each_time(self):
        first = ChoiceLine("Legacy", None, key="first")
        second = ChoiceLine("Legacy", None, key="second")
        card = card_with(choices=[first, second])
        assert len(card.detail_rows[-1].parts) == 2
        first.href = "/first/"
        second.href = "/second/"
        second.dismiss_href = "/dismiss-second/"
        html = card_html(card)
        assert html.find("form", action="/dismiss-second/")
        assert hide_dismissed({"first"}, card) == 1
        row = card.detail_rows[-1]
        assert [part.value for part in row.parts] == [second]
        assert card_html(card).find("a", href="/second/")
        assert not card_html(card).find("a", href="/first/")

    def test_equal_counters_are_not_added_together(self):
        card = card_with(
            counters=[
                CounterLine(
                    name="Marks",
                    value=2,
                    tallied=2,
                    href="/marks/first/",
                    assignment_id="first",
                ),
                CounterLine(
                    name="Marks",
                    value=3,
                    tallied=3,
                    href="/marks/second/",
                    assignment_id="second",
                ),
            ]
        )
        assert row_text(card.detail_rows[0]) == "2, 3"
        html = card_html(card)
        assert html.find("form", action="/marks/first/")
        assert html.find("form", action="/marks/second/")

    def test_an_explicit_separation_requires_both_key_and_reason(self):
        for key, reason in [("", "Different meaning"), ("scope", " ")]:
            with pytest.raises(ValueError, match="key and a reason"):
                Separation(key, reason)
        part = RowPart(PartKind.CHOICE, ChoiceLine("Legacy", "Ash"))
        exception = Separation(
            "separate-meaning", "This heading describes a different rule."
        )
        rows = compose_rows(
            [
                Contribution("model", "Legacy", part),
                Contribution("model", "Legacy", part, exception),
                Contribution("other-model", "Legacy", part),
            ]
        )
        assert len(rows) == 3
        assert rows[1].separation == exception

    def test_unknown_part_kinds_fail_instead_of_silently_splitting_or_disappearing(
        self,
    ):
        with pytest.raises(ValueError, match="Unsupported row part"):
            RowPart("future-kind", object())


class TestOwnersAndSurfaces:
    def test_two_identically_named_items_keep_their_own_choices_and_controls(self):
        kit = [
            AssignableLine(
                name="Rig",
                id=str(index),
                choices=[
                    ChoiceLine("Colour", "Red", href=f"/colour/{index}/"),
                    ChoiceLine("Colour", "Blue", href=f"/other-colour/{index}/"),
                ],
            )
            for index in range(2)
        ]
        card = card_with(equipment=kit, choices=[ChoiceLine("Colour", "Green")])
        assert kit[0].other_choice_rows[0].owner != kit[1].other_choice_rows[0].owner
        assert all(len(item.other_choice_rows[0].parts) == 2 for item in kit)
        html = card_html(card)
        assert all(html.find("a", href=f"/colour/{index}/") for index in range(2))
        assert all(html.find("a", href=f"/other-colour/{index}/") for index in range(2))
        assert [(group.label, group.text) for group in detail_groups(card)] == [
            ("Gear", "Rig, Rig"),
            ("Colour", "Green"),
            ("Rig — Colour", "Red, Blue"),
            ("Rig — Colour", "Red, Blue"),
        ]

    def test_weapons_group_their_own_questions_on_screen_and_paper(self):
        card = card_with(
            weapons=[
                WeaponLine(
                    name="Launcher",
                    base_rating=0,
                    id=str(index),
                    choices=[
                        ChoiceLine("Colour", "Red", href=f"/red/{index}/"),
                        ChoiceLine("Colour", "Blue", href=f"/blue/{index}/"),
                    ],
                )
                for index in range(2)
            ]
        )
        html = card_html(card)
        assert all(html.find("a", href=f"/red/{index}/") for index in range(2))
        assert all(html.find("a", href=f"/blue/{index}/") for index in range(2))
        assert html.get_text().count("Colour:") == 2
        printed = Template(
            CottonCompiler().process('<c-n26.print.weapons :card="card" />')
        ).render(Context({"card": card}))
        assert printed.count("Colour:") == 2
        assert printed.count("Red, Blue") == 2

    def test_gang_rules_and_dynamic_choices_share_the_same_composer(self):
        sheet = GangSheet(
            name="Gang",
            gang_type="House",
            rating=0,
            credits=0,
            wealth=0,
            rules=[AssignableLine("Stubborn")],
            choices=[ChoiceLine("Rules", "Tough")],
        )
        assert [(row.label, row_text(row)) for row in sheet.detail_rows] == [
            ("Rules", "Stubborn, Tough")
        ]
        assert "Rules: Stubborn, Tough" in render_gang_sheet(sheet)

    def test_choice_only_detail_lists_combine_and_keep_restore_controls(self):
        choices = [
            ChoiceLine("Legacy", "Ash", href="/ash/"),
            ChoiceLine(
                "Legacy", None, dismissed=True, restore_href="/restore/", back="/back/"
            ),
        ]
        html = BeautifulSoup(
            Template(
                CottonCompiler().process('<c-n26.choice-slots :choices="choices" />')
            ).render(Context({"choices": choices})),
            "html.parser",
        )
        assert len(html.select("dt")) == 1
        assert html.find("a", href="/ash/")
        assert html.find("form", action="/restore/")

    def test_readonly_has_one_heading_and_no_choice_or_dismissal_controls(self):
        card = card_with(
            choices=[ChoiceLine("Legacy", "Ash"), ChoiceLine("Legacy", None)]
        )
        html = card_html(card, "readonly")
        assert (
            len([dt for dt in html.select("dt") if dt.get_text(strip=True) == "Legacy"])
            == 1
        )
        assert "Ash" in html.get_text()
        assert not html.select("a, form, button")

    @pytest.mark.parametrize("kind", list(PartKind))
    def test_every_part_kind_has_html_print_and_text_support(self, kind):
        card = card_with(
            **{
                PartKind.NAMES: {"rules": [AssignableLine("Sentinel")]},
                PartKind.GEAR: {
                    "gear_groups": [GearGroup("Kit", [AssignableLine("Sentinel")])]
                },
                PartKind.COUNTER: {"counters": [CounterLine(name="Sentinel", value=7)]},
                PartKind.CHOICE: {"choices": [ChoiceLine("Legacy", "Sentinel")]},
            }[kind]
        )
        expected = "7" if kind == PartKind.COUNTER else "Sentinel"
        assert expected in card_html(card).get_text()
        assert any(expected in group.text for group in detail_groups(card))
        assert expected in "\n".join(render_model_card(card))
