from itertools import groupby


def group_select(form, field, key=lambda x: x):
    formfield = form.fields[field]
    groups = groupby(
        formfield.queryset,
        key=key,
    )

    label = (
        formfield.label_from_instance
        if hasattr(formfield, "label_from_instance")
        else lambda x: str(x)
    )

    choices = [
        (cat, [(item.id, label(item)) for item in items]) for cat, items in groups
    ]

    resolved_widget = (
        formfield.widget.widget
        if hasattr(formfield.widget, "widget")
        else formfield.widget
    )

    if not resolved_widget.__class__.__name__.endswith("Multiple"):
        formfield.widget.choices = [
            ("", "---------"),
        ] + choices
    else:
        formfield.widget.choices = choices
