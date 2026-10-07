import json
from collections import Counter
from pathlib import Path

import pytest
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django_cotton.templatetags._component import CottonComponentNode

from scripts import check_n26_alpine as guard

pytestmark = pytest.mark.core

PAGE = "n26/core/templates/n26/page.html"


def count(html):
    return len(guard.scan(html)[0])


@pytest.mark.parametrize(
    "html, expected",
    [
        ('<div x-data="{}" @click="a" x-on:keydown="b"></div>', 3),
        ('<div :class="a" :aria-expanded="b"></div>', 2),
        ('<template x-for="i in xs" :key="i"></template>', 2),
        # On a Cotton tag, :attr is Python and ::attr renders as Alpine.
        ('<c-ui.button ::aria-expanded="open" :disabled="True" />', 1),
        ('<c-n26.icon :items="menu_" ::class="{x: y}" x-on:click="f()" />', 2),
        ('<c-vars :open="False" :items="None" />', 0),
        # Glued to a template tag on either side.
        ('<div {% if a %}x-data="{}"{% endif %} x-cloak{% endif %}></div>', 2),
        ('<div{% if a %} x-init="f()"{% endif %}></div>', 1),
        # Not Alpine: container query classes, text, comments, scripts, SVG.
        ('<div class="@2xl:flex x-foo">x-data="no" @click="no"</div>', 0),
        ('{# <div x-data></div> #}<!-- <a @click="x"> -->', 0),
        ("{% comment %}<a x-show='a'>{% endcomment %}", 0),
        ('<script>el.setAttribute("x-data", "{}") // <b x-show="a"></script>', 0),
        ('<svg><use xlink:href="#i" x="1"/></svg>', 0),
    ],
)
def test_scan_counts_alpine_attributes(html, expected):
    assert count(html) == expected


@pytest.mark.parametrize(
    "html, expected",
    [
        ('{% if a %}<a @click="x" @focus="y">{% else %}<b @click="x">{% endif %}', 2),
        ('{% if a %}<a @click="x">{% elif b %}<b x-a x-b x-c>{% else %}{% endif %}', 3),
        # An if with no else is counted as drawn.
        ('<i x-data>{% if a %}<a @click="x">{% endif %}', 2),
        (
            "{% if a %}{% if b %}<a x-a x-b>{% else %}<a x-a>{% endif %}"
            "{% else %}<b x-a>{% endif %}",
            2,
        ),
    ],
)
def test_per_render_counts_largest_branch(html, expected):
    directives, _, branches = guard.scan(html)
    assert guard.per_render([(pos, 1) for pos in directives], branches) == expected


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def tree(tmp_path):
    """A repo with one page and one override, and a fake kit beside it."""
    kit = tmp_path / "kit"
    ui = kit / "cotton/ui"
    write(ui / "menu/index.html", '<div x-data="m()"><c-ui.menu.item /></div>')
    write(ui / "menu/item.html", '<a @click="x" @focus="y"></a>')
    write(ui / "mode_toggle.html", "<b x-data></b>")
    write(ui / "badge.html", "<span></span>")
    for tag in guard.UNCHARGED_TAGS:
        write(ui / f"{tag.removeprefix('ui.')}.html", "<nav x-data></nav>")
    root = tmp_path / "repo"
    write(
        root / "n26/core/templates/cotton/ui/mode_toggle.html",
        '<b x-data x-init="a" x-show="b"></b>',
    )
    write(
        root / PAGE,
        "<c-ui.menu /><c-ui.menu.item /><c-ui.mode-toggle /><c-ui.badge />"
        "<c-ui.breadcrumbs /><c-ui.alert />",
    )
    write(root / "n26/designsystem/templates/demo.html", "<c-ui.menu />")
    baseline = tmp_path / "baseline.json"

    def run(*argv):
        guard.main(
            [
                "--root",
                str(root),
                "--kit-templates",
                str(kit),
                "--baseline",
                str(baseline),
                *argv,
            ]
        )

    return {"root": root, "kit": kit, "ui": ui, "baseline": baseline, "run": run}


def test_kit_weights_follow_overrides_nesting_and_names(tree):
    kit = guard.Kit(tree["root"], tree["kit"])

    assert kit.weight("ui.menu.item") == 2
    assert kit.weight("ui.menu") == 3  # its own x-data plus the nested item
    # The override replaces the kit's copy, and Cotton snake-cases names.
    assert kit.resolve("ui.mode-toggle") == kit.resolve("ui.mode_toggle")
    assert kit.resolve("ui.mode-toggle").is_relative_to(tree["root"])
    assert kit.weight("ui.mode-toggle") == 3


def test_kit_resolves_flat_files_before_index_files(tree):
    # Cotton asks every root for x.html before it asks for x/index.html.
    write(tree["root"] / "n26/core/templates/cotton/ui/menu/index.html", "<a>")
    write(tree["ui"] / "menu.html", "<a x-data>")
    kit = guard.Kit(tree["root"], tree["kit"])

    assert kit.resolve("ui.menu") == tree["ui"] / "menu.html"


def test_kit_weight_survives_a_nesting_cycle(tree):
    write(tree["ui"] / "a.html", "<i x-a></i><c-ui.b />")
    write(tree["ui"] / "b.html", "<i x-b></i><c-ui.a />")
    kit = guard.Kit(tree["root"], tree["kit"])

    # Each counts the other once, whichever is weighed first.
    assert kit.weight("ui.a") == 2
    assert kit.weight("ui.b") == 2


def test_inventory_charges_kit_uses_but_not_chrome_or_gallery(tree):
    kit = guard.Kit(tree["root"], tree["kit"])
    counts, uses = guard.inventory(tree["root"], kit)

    # The override is first-party source, so it also counts as direct.
    assert counts == {
        "n26/core/templates/cotton/ui/mode_toggle.html": {"direct": 3, "kit": 0},
        PAGE: {"direct": 0, "kit": 8},
    }
    assert uses[PAGE] == Counter(
        {"ui.menu": 1, "ui.menu.item": 1, "ui.mode-toggle": 1, "ui.badge": 1}
    )


def test_unresolved_kit_tag_fails_the_run(tree):
    write(tree["root"] / PAGE, "<c-ui.renamed />")

    with pytest.raises(SystemExit, match="ui.renamed"):
        tree["run"]("--update")


def test_unresolved_kit_tag_in_the_gallery_fails_the_run(tree):
    write(tree["root"] / "n26/designsystem/templates/demo.html", "<c-ui.renamed />")

    with pytest.raises(SystemExit, match="ui.renamed"):
        tree["run"]("--update")


def test_uncharged_tag_over_its_cap_fails_the_run(tree):
    write(tree["ui"] / "alert.html", "<div x-a x-b x-c x-d></div>")

    with pytest.raises(SystemExit, match=r"ui.alert 4 \(cap 3\)"):
        tree["run"]("--update")


def test_check_refuses_a_baseline_before_format_2(tree):
    tree["baseline"].write_text(json.dumps({PAGE: 8}))

    with pytest.raises(SystemExit, match="Run with --update"):
        tree["run"]()

    tree["run"]("--update")
    data = json.loads(tree["baseline"].read_text())
    assert data["format"] == 2
    assert data["templates"][PAGE] == {"direct": 0, "kit": 8}
    assert data["weights"]["ui.badge"] == 0
    tree["run"]()


def test_kit_weight_change_fails_check_and_update_accepts_it(tree, capsys):
    tree["run"]("--update")
    write(tree["ui"] / "menu/item.html", '<a @click="x" @focus="y" @blur="z"></a>')

    with pytest.raises(SystemExit, match="ui.menu.item 2→3"):
        tree["run"]()

    tree["run"]("--update")
    assert "weight ui.menu.item 2→3" in capsys.readouterr().out
    assert json.loads(tree["baseline"].read_text())["templates"][PAGE]["kit"] == 10
    tree["run"]()


def test_kit_weight_rising_from_zero_counts_as_a_weight_change(tree):
    tree["run"]("--update")
    write(tree["ui"] / "badge.html", "<span x-data></span>")

    with pytest.raises(SystemExit, match="ui.badge 0→1"):
        tree["run"]()
    tree["run"]("--update")


def test_new_kit_tag_must_be_recorded_before_its_weight_can_change(tree):
    tree["run"]("--update")
    write(tree["ui"] / "card.html", "<div></div>")
    page = tree["root"] / PAGE
    write(page, page.read_text() + "<c-ui.card />")

    with pytest.raises(SystemExit, match="no recorded weight: ui.card 0"):
        tree["run"]()
    tree["run"]("--update")
    assert json.loads(tree["baseline"].read_text())["weights"]["ui.card"] == 0

    write(tree["ui"] / "card.html", "<div x-data></div>")
    with pytest.raises(SystemExit, match="ui.card 0→1"):
        tree["run"]()
    tree["run"]("--update")


def test_new_kit_use_is_refused_even_with_update(tree):
    tree["run"]("--update")
    page = tree["root"] / PAGE
    write(page, page.read_text() + "<c-ui.menu.item />")

    with pytest.raises(SystemExit, match="React island"):
        tree["run"]("--update")


def test_new_kit_use_is_refused_when_a_weight_falls_to_make_room(tree, capsys):
    tree["run"]("--update")
    write(tree["ui"] / "menu/item.html", '<a @click="x"></a>')
    page = tree["root"] / PAGE
    write(page, page.read_text() + "<c-ui.menu.item />")
    capsys.readouterr()

    # The page is 7 at the new weights, under its ceiling of 8, but 10 at the
    # recorded ones.
    with pytest.raises(SystemExit, match="React island"):
        tree["run"]("--update")
    assert (
        f"{PAGE}: 10 kit Alpine at the recorded weights (ceiling 8)"
        in capsys.readouterr().out
    )


def test_alpine_added_to_an_override_is_refused_even_with_update(tree):
    tree["run"]("--update")
    write(
        tree["root"] / "n26/core/templates/cotton/ui/mode_toggle.html",
        '<b x-data x-init="a" x-show="b" x-cloak></b>',
    )

    with pytest.raises(SystemExit, match="React island"):
        tree["run"]("--update")


def test_alpine_removed_from_an_override_is_recorded_by_update(tree, capsys):
    tree["run"]("--update")
    write(tree["root"] / "n26/core/templates/cotton/ui/mode_toggle.html", "<b x-data>")

    with pytest.raises(SystemExit, match="ui.mode-toggle 3→1"):
        tree["run"]()
    tree["run"]("--update")
    assert f"{PAGE} kit 8→6" in capsys.readouterr().out


def test_new_direct_alpine_is_refused_even_with_update(tree):
    tree["run"]("--update")
    page = tree["root"] / PAGE
    write(page, page.read_text() + '<div x-data="{}"></div>')

    with pytest.raises(SystemExit, match="React island"):
        tree["run"]("--update")


def test_update_prints_each_lowered_ceiling(tree, capsys):
    tree["run"]("--update")
    write(tree["root"] / PAGE, "<c-ui.badge />")
    capsys.readouterr()

    tree["run"]("--update")

    assert f"{PAGE} kit 8→0" in capsys.readouterr().out
    assert PAGE not in json.loads(tree["baseline"].read_text())["templates"]


def used_kit_tags():
    tags = set(guard.UNCHARGED_TAGS)
    for path in (guard.ROOT / guard.SCAN_DIR).rglob("*.html"):
        _, components, _ = guard.scan(path.read_text())
        tags.update(t for _, t in components if t.startswith(guard.KIT_PREFIX))
    return sorted(tags)


def django_origin(tag):
    name = CottonComponentNode._generate_component_template_path(tag, None)
    try:
        template = get_template(name)
    except TemplateDoesNotExist:
        template = get_template(name.removesuffix(".html") + "/index.html")
    return Path(template.origin.name)


def test_kit_resolution_matches_the_django_template_loader():
    kit = guard.Kit(guard.ROOT)
    mismatched = {
        tag: (kit.resolve(tag), django_origin(tag))
        for tag in used_kit_tags()
        if kit.resolve(tag) != django_origin(tag)
    }

    assert mismatched == {}


def test_real_tree_resolves_the_dropdown_override_and_every_uncharged_tag():
    kit = guard.Kit(guard.ROOT)

    dropdown = kit.resolve("ui.dropdown")
    assert dropdown == guard.ROOT / "n26/core/templates/cotton/ui/dropdown/index.html"
    assert kit.weight("ui.dropdown") > 0
    for tag in guard.UNCHARGED_TAGS:
        assert kit.resolve(tag) is not None, tag
