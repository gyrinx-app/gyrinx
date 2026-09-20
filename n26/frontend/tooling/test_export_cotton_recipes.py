from n26.frontend.tooling.export_cotton_recipes import recipes


def test_icon_recipes_keep_their_svg_geometry():
    icons = recipes()["icons"]

    assert [element["tag"] for element in icons["search"]] == ["path", "circle"]
    assert [element["tag"] for element in icons["x"]] == ["path", "path"]
