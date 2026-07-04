# Background task registry: the silent dev/prod split, and a better abstraction

## The incident

The Phase 8 cost-pinning PR (#1946) shipped a new background task, `backfill_pins`
(`gyrinx/core/tasks.py`), decorated with Django's `@task`, exercised by tests, and
run happily in dev — and it could not be enqueued in production at all. The deep
review caught it pre-merge; it would otherwise have been discovered by ops running
the flagship Phase 8 command against prod.

## Why this happens (and will happen again)

Declaring a background task is currently a **two-step ritual split across two
files with nothing coupling them**:

1. Define the function with `@task` in `gyrinx/core/tasks.py`.
2. Add a `TaskRoute(fn)` entry to `gyrinx/tasks/registry.py`.

Only the **production** backend enforces step 2:

- `PubSubBackend.enqueue()` (`gyrinx/tasks/backend.py:100-104`) looks the task up
  in the registry and raises `ValueError: Task '<name>' not registered` for
  anything missing.
- Topic provisioning (`gyrinx/tasks/provisioning.py`) also iterates the registry,
  so an unregistered task has no Pub/Sub topic even if the enqueue were reached.

Meanwhile the environments where code actually gets exercised never consult the
registry:

- Dev and tests use `ImmediateBackend` (`settings.py:476-478`), which executes
  whatever it's handed — registry never read.
- Tests conventionally call `some_task.func(...)` directly, bypassing enqueue
  entirely.

So the invariant is enforced **only** in the one environment nobody runs before
merge. Every future task author walks the same trap: everything green locally,
dead on arrival in prod. This is a classic "the check lives where the failure
happens, not where the mistake happens" design.

## Options considered

### A. Django system check — the backstop (recommended, do immediately)

A `django.core.checks` check (registered in `gyrinx/tasks/apps.py` or similar)
that:

- imports the known task modules (`gyrinx.core.tasks`, and any future ones),
- collects every `django.tasks.Task` instance defined there,
- **errors** if any is missing from the registry (`gyrinx.tasks.registry`),
- **errors** in the other direction too: a registry entry whose function has been
  renamed/deleted (catches refactors),
- optionally warns on config smells (e.g. an `ack_deadline` shorter than a task's
  plausible runtime is unknowable, but duplicate routes are checkable).

Why a system check rather than a test: `manage runserver`, `manage migrate`,
`manage check --deploy`, and CI all run checks automatically — the mistake is
caught seconds after it's made, in the author's own dev loop, with a message
saying exactly which file to edit. (A pytest guard would work too, but checks
fire earlier and in more workflows; there's no reason not to have the check *be*
the single source of enforcement.)

Cost: ~40 lines, zero production behaviour change, no migration.

### B. Single-point declaration — the better abstraction (recommended, follow-up)

Make registration a side effect of declaration. A thin project decorator:

```python
# gyrinx/tasks/decorators.py
def gyrinx_task(*, ack_deadline: int | None = None, schedule: str | None = None):
    def wrap(fn):
        t = django_task(fn)          # Django's @task
        register_route(TaskRoute(t, ack_deadline=ack_deadline, schedule=schedule))
        return t
    return wrap
```

Usage becomes one declaration, in one place, carrying its own config:

```python
@gyrinx_task(ack_deadline=600)
def backfill_pins(after_id=None, batch_size=250): ...
```

`registry.py` shrinks to a list of **task modules** to import (the lazy-import
shape it already has, for the same circular-import reasons); the per-task entries
disappear. Forgetting to register a task in a known module becomes structurally
impossible. The remaining smaller trap — adding a brand-new tasks *module* and
forgetting to list it — is exactly what check (A)'s "unregistered Task instance"
scan catches, so A and B compose: B makes the common case impossible, A polices
the rare case.

Migration path: mechanical — move each `TaskRoute(fn, ...)` kwarg onto the
corresponding `@gyrinx_task(...)`; the registry keeps its public helpers
(`get_task`, `get_all_tasks`) so `backend.py` and `provisioning.py` don't change.

### C. Backend parity in dev (optional, complements A)

Wrap `ImmediateBackend` in a thin subclass whose `enqueue()` consults the
registry before delegating. Dev then fails exactly like prod at the first real
enqueue. Cheap, but it only catches code paths that actually enqueue during
manual dev use — tests calling `.func` still bypass it — so it supplements
rather than replaces A. Worth doing if A ever proves insufficient.

### D. Full auto-discovery (rejected)

Scan all installed apps for `Task` instances and register everything implicitly,
no registry at all. Rejected: the registry deliberately carries per-task
configuration (ack deadlines, cron schedules) and is the explicit provisioning
surface for Pub/Sub topics — making topic creation an implicit side effect of
"someone imported a module" is the wrong direction for infrastructure that costs
money and has IAM surface.

## Recommendation

1. **Now**: land the system check (A). It turns this whole class of bug into a
   red error in the author's terminal within seconds of making the mistake.
2. **Follow-up**: adopt the declaration-owned registration (B) so the two-file
   ritual disappears entirely, keeping A as the tripwire for new task modules.

## References

- Incident: PR #1946 review (Phase 8, cost-pinning programme #1826) — HIGH
  finding, fixed by registering `backfill_pins` with `ack_deadline=600`.
- Enforcement point: `gyrinx/tasks/backend.py:100-104`.
- Provisioning: `gyrinx/tasks/provisioning.py` (`get_all_tasks()`).
- Registry: `gyrinx/tasks/registry.py` (lazy `_get_tasks()` to avoid circular
  imports — any solution must keep that property).
