"""Personal Trade Points granted by content, accounted for by the ledger.

Original models spend during founding. Models recruited after its first
completion spend through an individual hire-time activity. Both draw the
same authored counter and retain lifetime spend across corrections. Refunds
follow the original purchase and buyer; sales do not return Trade Points.
"""

from dataclasses import dataclass


def budget_granted(computed):
    """What this model may spend at founding, read off its computed card.

    No query where nothing raises the counter, which is every model in
    every gang whose books grant no such allowance: the contributions are
    already on the card, and only one that names this counter is worth
    asking the library about.

    Pinned to the standard counter, as every reader of one is: counter
    names are unique per pack, so a homebrew pack's counter of the same
    name must not stand in for it. That is one query, and only where a
    contribution named the counter — a model with none pays nothing to
    find that out.
    """
    from n26.library.standard_content import founding_budget_counter

    if not _names_the_counter(computed):
        return 0
    standard = founding_budget_counter()
    if standard is None:
        return 0
    return _raised_by(computed, standard)


def _names_the_counter(computed):
    """Whether anything on this card raises the founding allowance, by
    the counter's name alone. Settled without a query, which is what
    keeps a model with no allowance costing what it always did."""
    from n26.library.standard_content import FOUNDING_BUDGET_COUNTER

    wanted = FOUNDING_BUDGET_COUNTER.casefold()
    return any(
        contribution.counter.name.casefold() == wanted
        for contribution in computed.counter_contributions
    )


def _raised_by(computed, standard):
    """What this card raises the standard counter by. Pinned to the row
    rather than the name: a homebrew pack's counter called the same thing
    is a different counter and grants nothing here."""
    return sum(
        contribution.amount
        for contribution in computed.counter_contributions
        if contribution.counter.pk == standard.pk
    )


@dataclass(frozen=True)
class FoundingBudget:
    """The model's grant and lifetime spend while its spending action is open."""

    activity: object
    granted: int
    spent: int

    @property
    def remaining(self):
        """What is left. Goes negative where the owner said they meant to
        overspend, which is what the question before such a purchase is
        for: Trade Points inform, and only credits are refused."""
        return self.granted - self.spent

    @property
    def title(self):
        from n26.core.models import Activity

        return (
            "Hire-time Trade Points"
            if self.activity.kind == Activity.Kind.HIRE_TIME
            else "Founding Trade Points"
        )

    @property
    def action_label(self):
        return self.activity.get_kind_display()

    @property
    def facts(self):
        """The budget as a tally: what it holds, what has gone, what is
        left. Drawn by ``<c-n26.tally>``, which the Visit Trading Post
        card and the overspend question draw too — one arithmetic, one
        shape."""
        from n26.core.confirm import Fact

        return (
            Fact("Available", str(self.granted)),
            Fact("Spent", str(self.spent)),
            Fact("Remaining", str(self.remaining), ruled=True, strong=True),
        )


def budget_for(gang, miniature, computed):
    """The available personal balance, or None without a grant or open action."""
    from n26.core.models import Activity
    from n26.core.reconcile import trade_points_spent_by_kind

    granted = budget_granted(computed)
    if granted <= 0:
        return None
    if miniature.membership_id in _cloned_memberships([miniature]):
        return None
    activity = personal_activity_for(gang, miniature)
    if activity is None:
        return None
    return FoundingBudget(
        activity=activity,
        granted=granted,
        spent=trade_points_spent_by_kind(
            gang, (Activity.Kind.FOUNDING, Activity.Kind.HIRE_TIME), miniature
        ),
    )


def _models_for(computed, models=None):
    """Reuse the roster where supplied; card-only callers fetch it once."""
    if models is None:
        from n26.core.models import Miniature

        models = Miniature.objects.filter(pk__in=computed).select_related("membership")
    return {str(model.pk): model for model in models}


def grants_by_model(computed, *, models=None):
    """Read authored personal grants once for all computed cards."""
    from n26.library.standard_content import founding_budget_counter

    named = {str(pk): fold for pk, fold in computed.items() if _names_the_counter(fold)}
    if not named:
        return {}
    standard = founding_budget_counter()
    if standard is None:
        return {}
    models = _models_for(named, models)
    cloned = _cloned_memberships(models.values())
    return {
        pk: _raised_by(fold, standard)
        for pk, fold in named.items()
        if models[pk].membership_id not in cloned
    }


def _cloned_memberships(models):
    """Copied models retain possessions, rather than receiving a new allowance."""
    from n26.core.models import LedgerEvent

    return set(
        LedgerEvent.objects.filter(
            assignment_id__in=[model.membership_id for model in models],
            kind=LedgerEvent.Kind.CLONED,
        ).values_list("assignment_id", flat=True)
    )


def budgets_by_model(gang, computed, *, grants=None, models=None):
    """Read open personal balances in batches, reusing the prepared roster."""
    from n26.core.models import Activity
    from n26.core.reconcile import trade_points_spent_by_model_for_kind

    named = {
        str(model_id): fold
        for model_id, fold in computed.items()
        if _names_the_counter(fold)
    }
    if not named:
        return {}
    models = _models_for(named, models)
    activities = {
        model_id: personal_activity_for(gang, model)
        for model_id, model in models.items()
        if model_id in named
    }
    if not any(activities.values()):
        return {}
    grants = (
        grants_by_model(computed, models=models.values()) if grants is None else grants
    )
    spent = {
        str(model_id): total
        for model_id, total in trade_points_spent_by_model_for_kind(
            gang, (Activity.Kind.FOUNDING, Activity.Kind.HIRE_TIME)
        ).items()
    }
    budgets = {}
    for model_id in named:
        activity = activities.get(str(model_id))
        if activity is None:
            continue
        granted = grants.get(str(model_id), 0)
        if granted <= 0:
            continue
        budgets[str(model_id)] = FoundingBudget(
            activity=activity, granted=granted, spent=spent.get(str(model_id), 0)
        )
    return budgets


def personal_activity_for(gang, miniature):
    """Select the model's session using the original founding boundary."""
    from n26.core.models import Activity

    boundary = gang.founding_completed_at()
    if boundary is None or miniature.membership.created <= boundary:
        return gang.open_activity(Activity.Kind.FOUNDING)
    return gang.open_activity(Activity.Kind.HIRE_TIME, miniature)


@dataclass(frozen=True)
class HireTimeState:
    """A later recruit's available, open or completed spending opportunity."""

    activity: object = None

    @property
    def act(self):
        if self.activity is None:
            return "start"
        return "finish" if self.activity.is_open else "reopen"

    @property
    def activity_id(self):
        return str(self.activity.pk) if self.activity is not None else ""

    @property
    def button_label(self):
        return {
            "start": "Spend hire-time TP",
            "finish": "Complete action",
            "reopen": "Reopen for correction",
        }[self.act]


def hire_time_states(gang, models, computed, *, grants=None):
    """Read pending and completed recruit actions with a fixed query count."""
    computed = {str(pk): fold for pk, fold in computed.items()}
    named = {
        str(model.pk): model
        for model in models
        if _names_the_counter(computed[str(model.pk)])
    }
    if not named:
        return {}
    boundary = gang.founding_completed_at()
    if boundary is None:
        return {}
    later = {
        pk: model
        for pk, model in named.items()
        if not model.membership.archived and model.membership.created > boundary
    }
    if not later:
        return {}
    grants = grants_by_model(computed, models=models) if grants is None else grants
    latest = gang.hire_time_activities()
    return {
        pk: HireTimeState(latest.get(model.pk))
        for pk, model in later.items()
        if grants.get(pk, 0) > 0
    }
