from n26.frontend.tooling.export_cotton_recipes import recipes


def test_icon_recipes_keep_their_svg_geometry():
    icons = recipes()["icons"]

    assert [element["tag"] for element in icons["search"]] == ["path", "circle"]
    assert [element["tag"] for element in icons["x"]] == ["path", "path"]


def test_form_recipes_keep_the_cotton_controls_and_toggle_layout():
    form = recipes()

    assert "focus-ring" in form["input"]["control"]
    assert form["switch"]["trackChecked"] == "bg-accent"
    assert form["switch"]["thumbChecked"] == "translate-x-[1.375rem]"
    assert "justify-between" in form["field"]["toggleRow"]
    assert "shrink-0" in form["field"]["toggleControl"]
