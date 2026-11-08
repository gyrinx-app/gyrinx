"""Check assignable and condition model wiring during startup.

Every assignable kind needs an Assignment field. Reject incomplete wiring
before content can be created that cannot be assigned.
"""

from django.apps import apps
from django.core.checks import Error, register


@register()
def every_assignable_has_a_column(app_configs, **kwargs):
    from n26.core.models.assignment import ASSIGNABLE_FIELDS
    from n26.library.models.assignable import Assignable

    declared = {path.lower() for path in ASSIGNABLE_FIELDS.values()}
    found = {
        f"{model._meta.app_label}.{model._meta.model_name}"
        for model in apps.get_models()
        if issubclass(model, Assignable)
    }

    errors = []
    for label in sorted(found - declared):
        errors.append(
            Error(
                f"{label} is an Assignable but Assignment has no column for it.",
                hint=(
                    "Add it to n26.models.assignment.ASSIGNABLE_FIELDS, add a "
                    "matching nullable ForeignKey to Assignment, and make a "
                    "migration — the exactly-one-assignable constraint is "
                    "generated from that list."
                ),
                id="n26.E001",
            )
        )
    for label in sorted(declared - found):
        errors.append(
            Error(
                f"ASSIGNABLE_FIELDS names {label}, which is not an Assignable.",
                hint="Remove it, or make that model inherit the Assignable mixin.",
                id="n26.E002",
            )
        )
    return errors


@register()
def every_condition_is_folded(app_configs, **kwargs):
    """Require every condition model in its scope's CONDITIONS tuple.

    as_selector reads only those reverse relations. Missing registration would
    store authored conditions without applying them.
    """
    from n26.library.models.modifier import (
        TargetsAttachedWeapon,
        TargetsGang,
        TargetsMiniature,
        TargetsWeapons,
    )

    errors = []
    for scope_model in (
        TargetsMiniature,
        TargetsWeapons,
        TargetsAttachedWeapon,
        TargetsGang,
    ):
        declared = set(getattr(scope_model, "CONDITIONS", ()))
        found = {
            relation.get_accessor_name()
            for relation in scope_model._meta.related_objects
            if hasattr(relation.related_model, "as_condition")
        }
        for name in sorted(found - declared):
            errors.append(
                Error(
                    f"{scope_model.__name__}.{name} is a condition relation "
                    f"but {scope_model.__name__}.CONDITIONS does not fold it.",
                    hint=(
                        "Add the related name to the scope's CONDITIONS tuple "
                        "so as_selector() and __str__ fold its rows."
                    ),
                    id="n26.E003",
                )
            )
        for name in sorted(declared - found):
            errors.append(
                Error(
                    f"{scope_model.__name__}.CONDITIONS names {name!r}, which "
                    "is not a condition relation on that scope.",
                    hint=(
                        "Remove it, or give the condition model a scope FK "
                        "with that related_name and an as_condition() method."
                    ),
                    id="n26.E004",
                )
            )
    return errors
