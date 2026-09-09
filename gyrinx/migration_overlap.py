"""Find migrations on two branches that touch the same thing.

Two migrations written on separate branches know nothing of each other. Most
pairs are fine: each adds its own field or model, and the order they are
applied in cannot matter. The pairs that can go wrong touch the same model or
field, or one of them runs code against data the other changes. This module
reads the operations of both sets and reports those pairs, so the author hears
about it while the pull request is open rather than when a deploy fails.

It is a static reading of ``operations``, not a proof: it names the model and
field an operation declares, and for ``RunPython`` the models its source
fetches with ``get_model``. Code that reaches a model some other way is
reported as touching its whole app, which errs towards a warning.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

from django.db import migrations

# Operations that change what an existing name refers to. Anything else on
# the same model must be ordered against them.
_MODEL_RESHAPING = {"DeleteModel", "RenameModel", "AlterModelTable"}

_GET_MODEL = re.compile(
    r"""get_model\(\s*['"](?P<app>\w+)['"]\s*,\s*['"](?P<model>\w+)['"]"""
    r"""|get_model\(\s*['"](?P<dotted>\w+\.\w+)['"]"""
)


@dataclass(frozen=True)
class Touch:
    """One thing an operation reaches: a field, a model, or a whole app."""

    app: str
    model: str | None  # lower-cased; None when the scope could not be read
    field: str | None
    kind: str  # create, delete, reshape, add, remove, alter, meta, data
    operation: str  # the operation class, for the report

    def describe(self):
        target = self.app
        if self.model:
            target += f".{self.model}"
        if self.field:
            target += f".{self.field}"
        return f"{self.operation} on {target}"


@dataclass(frozen=True)
class Finding:
    severity: (
        str  # "blocks" — deploy or fresh database can fail; "review" — order may matter
    )
    base: tuple[str, str]
    branch: tuple[str, str]
    base_touch: Touch
    branch_touch: Touch
    reason: str


def _fields_of(obj):
    """Field names an index, constraint or option tuple names, if any."""
    names = getattr(obj, "fields", None)
    if names:
        return [name.lstrip("-") for name in names]
    return []


def _touches_of_code(app_label, operation):
    """Models a RunPython's forward function fetches; whole app if unreadable."""
    try:
        source = inspect.getsource(operation.code)
    except OSError, TypeError:
        source = ""
    found = []
    for match in _GET_MODEL.finditer(source):
        if match.group("dotted"):
            app, model = match.group("dotted").split(".")
        else:
            app, model = match.group("app"), match.group("model")
        found.append(Touch(app, model.lower(), None, "data", "RunPython"))
    if found:
        return found
    return [Touch(app_label, None, None, "data", "RunPython")]


def touches(app_label, operation):
    """Everything one operation reaches, as Touch records."""
    name = type(operation).__name__
    if isinstance(operation, migrations.SeparateDatabaseAndState):
        return [
            touch
            for op in [*operation.database_operations, *operation.state_operations]
            for touch in touches(app_label, op)
        ]
    if isinstance(operation, migrations.RunPython):
        return _touches_of_code(app_label, operation)
    if isinstance(operation, migrations.RunSQL):
        return [Touch(app_label, None, None, "data", "RunSQL")]

    model = getattr(operation, "model_name", None) or getattr(operation, "name", None)
    if isinstance(operation, migrations.CreateModel):
        return [Touch(app_label, operation.name.lower(), None, "create", name)]
    if isinstance(operation, migrations.DeleteModel):
        return [Touch(app_label, operation.name.lower(), None, "delete", name)]
    if isinstance(operation, migrations.RenameModel):
        return [
            Touch(app_label, operation.old_name.lower(), None, "reshape", name),
            Touch(app_label, operation.new_name.lower(), None, "reshape", name),
        ]
    if isinstance(operation, migrations.AlterModelTable):
        return [Touch(app_label, operation.name.lower(), None, "reshape", name)]
    if isinstance(operation, migrations.RenameField):
        return [
            Touch(app_label, model.lower(), operation.old_name, "reshape", name),
            Touch(app_label, model.lower(), operation.new_name, "reshape", name),
        ]
    if isinstance(operation, migrations.AddField):
        return [Touch(app_label, model.lower(), operation.name, "add", name)]
    if isinstance(operation, migrations.RemoveField):
        return [Touch(app_label, model.lower(), operation.name, "remove", name)]
    if isinstance(operation, migrations.AlterField):
        return [Touch(app_label, model.lower(), operation.name, "alter", name)]
    if isinstance(operation, (migrations.AddIndex, migrations.AddConstraint)):
        target = getattr(operation, "index", None) or getattr(
            operation, "constraint", None
        )
        fields = _fields_of(target)
        if fields:
            return [Touch(app_label, model.lower(), f, "meta", name) for f in fields]
        return [Touch(app_label, model.lower(), None, "meta", name)]
    if isinstance(operation, migrations.AlterUniqueTogether):
        fields = sorted({f for group in operation.unique_together or () for f in group})
        if fields:
            return [Touch(app_label, model.lower(), f, "meta", name) for f in fields]
        return [Touch(app_label, model.lower(), None, "meta", name)]
    if model:
        # AlterModelOptions, AlterModelManagers, RemoveIndex, RemoveConstraint,
        # AlterOrderWithRespectTo and any operation this module has not met.
        return [Touch(app_label, str(model).lower(), None, "meta", name)]
    return [Touch(app_label, None, None, "meta", name)]


def _judge(a: Touch, b: Touch):
    """Why two touches conflict, as (severity, reason); None when they don't."""
    if a.app != b.app:
        return None
    if a.model is None or b.model is None:
        # A data migration whose scope could not be read against anything in
        # the same app, or two of them.
        if a.kind == "data" or b.kind == "data":
            return ("review", "a data migration whose scope could not be read")
        return None
    if a.model != b.model:
        return None
    if a.kind == "create" or b.kind == "create":
        return ("blocks", "both branches create or reshape the same model")
    if a.operation in _MODEL_RESHAPING or b.operation in _MODEL_RESHAPING:
        return ("blocks", "one branch renames or deletes a model the other changes")
    if a.kind == "data" or b.kind == "data":
        return (
            "review",
            "a data migration runs against a model the other branch changes",
        )
    if a.field and b.field and a.field == b.field:
        return ("blocks", "both branches change the same field")
    if a.field is None and b.field is None and a.operation == b.operation:
        return ("review", "both branches change the same model-level option")
    return None


def overlaps(base_migrations, branch_migrations):
    """Findings for every conflicting pair between two sets of migrations.

    Each argument maps ``(app_label, name)`` to a loaded ``Migration``.
    """
    base_touches = [
        (key, touch)
        for key, migration in base_migrations.items()
        for op in migration.operations
        for touch in touches(key[0], op)
    ]
    branch_touches = [
        (key, touch)
        for key, migration in branch_migrations.items()
        for op in migration.operations
        for touch in touches(key[0], op)
    ]
    found = []
    seen = set()
    for base_key, a in base_touches:
        for branch_key, b in branch_touches:
            verdict = _judge(a, b)
            if verdict is None:
                continue
            severity, reason = verdict
            signature = (base_key, branch_key, a, b)
            if signature in seen:
                continue
            seen.add(signature)
            found.append(Finding(severity, base_key, branch_key, a, b, reason))
    found.sort(key=lambda f: (f.severity != "blocks", f.base, f.branch))
    return found
