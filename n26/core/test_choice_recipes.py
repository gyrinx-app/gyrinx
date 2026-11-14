"""Build-time choice recipes must work before any browser assets exist."""

from contextlib import ExitStack

from django.db import connections
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.templatetags import react
from n26.frontend.tooling.export_choice_recipes import choice_recipes
from n26.frontend.tooling.export_cotton_recipes import Elements, class_name, recipes


def test_export_bootstraps_without_a_manifest_or_database_queries(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(react, "BUILD", tmp_path / "unbuilt")

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Recipe generation must not resolve browser assets or query data"
        )

    monkeypatch.setattr(react, "_manifest", forbidden)
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(forbidden))
        exported = recipes()
    assert set(exported["choice"]) == {
        "picks",
        "rollResult",
        "rollTable",
        "divider",
        "die",
        "arrivalBlock",
        "arrivalQuestion",
        "nextPage",
    }
    assert exported["icons"]["dices"]
    assert exported["choice"]["nextPage"]["root"]
    assert exported["choice"]["nextPage"]["footer"]


def test_every_die_face_comes_from_its_cotton_pips():
    die = choice_recipes(Elements, class_name)["die"]
    for value in range(1, 7):
        rendered = Template(
            CottonCompiler().process(f'<c-n26.die value="{value}" />')
        ).render(Context())
        elements = Elements(rendered).elements
        assert die["root"] == class_name(elements[0][1])
        expected = die["faces"][str(value)]
        assert len(expected) == 9
        assert sum(expected) == value
        assert [die["filledPip"] if pip else die["pip"] for pip in expected] == [
            class_name(attrs) for _, attrs in elements[1:]
        ]


def test_choice_recipe_classes_do_not_contain_template_or_example_data():
    def inspect(value):
        if isinstance(value, dict):
            for child in value.values():
                inspect(child)
        elif isinstance(value, str):
            assert value
            assert not any(
                fragment in value for fragment in ("{{", "{%", "Example", "<", ">")
            )
            assert value == " ".join(value.split())

    inspect(choice_recipes(Elements, class_name))
