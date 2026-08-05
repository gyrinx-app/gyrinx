from collections.abc import Callable
from itertools import groupby


def group_select(form, field, key=lambda x: x, sort_groups_by=None):
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

    # Sort groups if sort_groups_by is provided
    if sort_groups_by is not None:
        choices.sort(key=lambda x: sort_groups_by(x[0]))

        # Merge adjacent groups with the same key after sorting
        merged_choices = []
        for i, (group_key, items) in enumerate(choices):
            if i > 0 and merged_choices and merged_choices[-1][0] == group_key:
                # Merge with the previous group
                merged_choices[-1] = (group_key, merged_choices[-1][1] + list(items))
            else:
                # Add as a new group
                merged_choices.append((group_key, list(items)))
        choices = merged_choices

    resolved_widget = (
        formfield.widget.widget
        if hasattr(formfield.widget, "widget")
        else formfield.widget
    )

    if not getattr(resolved_widget, "allow_multiple_selected", False):
        formfield.widget.choices = [
            ("", "---------"),
        ] + choices
    else:
        formfield.widget.choices = choices


def group_sorter(priority_name: str) -> Callable[[str], tuple]:
    def sort_groups_key(group_name):
        # Sort groups: gang's own house first, then alphabetically
        if group_name == priority_name:
            return (0, group_name)  # Gang's house comes first
        else:
            return (1, group_name)  # Other houses alphabetically

    return sort_groups_key
