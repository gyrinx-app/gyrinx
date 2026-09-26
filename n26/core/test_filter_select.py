from n26.core.templatetags.filter_select import filter_select_props


def options(count):
    return "".join(
        f'<option value="{index}"{" selected" if index == 2 else ""}>'
        f"Option {index}</option>"
        for index in range(count)
    )


def test_short_selects_stay_native_and_the_threshold_counts_options():
    short = f'<select name="thing">{options(14)}</select>'
    long = f'<select name="thing">{options(15)}</select>'

    assert filter_select_props(short, 15) is None
    assert filter_select_props(long, 15)["options"][2]["selected"] is True


def test_select_props_preserve_the_post_contract_and_plain_option_text():
    markup = """
        <select name="what-thing_skill" id="id_what-thing_skill" required
                data-union-of="thing" data-union-member="skill rule">
            <option value="" disabled selected>Choose &amp; filter</option>
            <option value="one">  One
                name </option>
            <option value="two" disabled>Two</option>
        </select>
    """

    props = filter_select_props(markup, 3, "Find one", "No matches")

    assert props == {
        "name": "what-thing_skill",
        "id": "id_what-thing_skill",
        "multiple": False,
        "required": True,
        "disabled": False,
        "attrs": {
            "data-union-of": "thing",
            "data-union-member": "skill rule",
        },
        "options": [
            {
                "value": "",
                "label": "Choose & filter",
                "selected": True,
                "disabled": True,
            },
            {
                "value": "one",
                "label": "One name",
                "selected": False,
                "disabled": False,
            },
            {
                "value": "two",
                "label": "Two",
                "selected": False,
                "disabled": True,
            },
        ],
        "placeholder": "Find one",
        "empty": "No matches",
    }


def test_a_single_select_uses_the_last_marked_option_like_the_browser():
    markup = """
        <select name="thing">
            <option value="first" selected>First</option>
            <option value="second" selected>Second</option>
        </select>
    """

    props = filter_select_props(markup, 2)

    assert [option["selected"] for option in props["options"]] == [False, True]


def test_an_unmarked_single_select_uses_the_first_enabled_option():
    markup = """
        <select name="thing">
            <option value="" disabled>Choose one</option>
            <option value="first">First</option>
            <option value="second">Second</option>
        </select>
    """

    props = filter_select_props(markup, 3)

    assert [option["selected"] for option in props["options"]] == [
        False,
        True,
        False,
    ]


def test_a_multiple_select_keeps_every_marked_option():
    markup = """
        <select name="thing" multiple>
            <option value="first" selected>First</option>
            <option value="second" selected>Second</option>
        </select>
    """

    props = filter_select_props(markup, 2)

    assert props["multiple"] is True
    assert [option["selected"] for option in props["options"]] == [True, True]
