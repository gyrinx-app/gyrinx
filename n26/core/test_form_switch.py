"""The form switch's opening state is a boolean the script can read."""

from n26.core.templatetags.form_switch import form_switch_props


def test_none_and_the_string_false_are_off():
    props = form_switch_props(
        name="foundable",
        checked=None,
        disabled="false",
        accent="false",
        size="nope",
        value="",
    )

    assert props == {
        "name": "foundable",
        "value": "on",
        "checked": False,
        "disabled": False,
        "accent": False,
        "size": "md",
        "className": "",
        "id": "",
    }


def test_the_string_true_and_a_known_size_are_kept():
    props = form_switch_props(checked="true", disabled=True, size="sm", value="yes")

    assert props["checked"] is True
    assert props["disabled"] is True
    assert props["accent"] is True
    assert props["size"] == "sm"
    assert props["value"] == "yes"
