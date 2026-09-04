from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from n26.core.models.abstract import Archived, Base, Owned, Rated

#: Where a queryset leaves what it read about the gang's open visit. Not
#: the property's own name: an annotation is set with ``setattr``, and a
#: property with no setter would refuse it.
_OPEN_VISIT_POINTS = "open_visit_points"


def open_visit_points(gang="pk"):
    """A subquery reading what a gang's open Visit Trading Post action
    brought, to annotate alongside the gang's own row.

    ``gang`` is the path from the queryset's model to the gang, so a
    fighter's queryset can ask on its gang's behalf.

    Nothing and nought are different states, and this keeps them apart:
    the figure is coalesced inside the subquery, so a null can only mean
    there is no open visit — never a visit that brought no points.
    """
    from n26.core.models import Action

    return Subquery(
        Action.objects.filter(
            gang=OuterRef(gang),
            kind=Action.Kind.TRADING_POST_VISIT,
            closed__isnull=True,
        )
        .annotate(brought=Coalesce("trade_points", Value(0)))
        .values("brought")[:1]
    )


class Gang(Base, Owned, Archived, Rated):
    """A player's gang."""

    name = models.CharField(max_length=200)
    gang_type = models.ForeignKey(
        "library.GangType", on_delete=models.PROTECT, related_name="gangs"
    )
    founding = models.OneToOneField(
        "n26.Assignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="founded",
        help_text=(
            "The gang-hosted assignment naming this gang's type — what a "
            "membership is to a model. Carries the gang's built-ins and "
            "its gang-wide modifiers."
        ),
    )
    starting_credits = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The budget, where one applies. Null means unlimited — the "
            "founding default: players buy what they own and the gang "
            "shows its rating. A ceiling is a campaign's choice, and only "
            "then is overspend refused."
        ),
    )
    credits = models.PositiveIntegerField(
        default=0,
        help_text="Cash in hand. Pinned: starting budget less everything spent.",
    )
    #: Nothing reads or writes this, and the column goes in the next
    #: deploy. It is kept for one because dropping a column the outgoing
    #: revision still reads gives every request that revision serves an
    #: error for the seconds the two overlap. The help text below still
    #: describes the figure as live; correcting it would take a
    #: migration of its own, for a field with one deploy left.
    starting_trade_points = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "A copy of what the open Visit Trading Post action brought, "
            "kept beside it. Empty when no visit is open. The action "
            "itself holds the figure the screens read."
        ),
    )
    colour = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Shown next to the gang's name wherever it is listed.",
    )
    #: The owner's own words about the gang — table agreements, standing
    #: reminders. Editor HTML, stored as written and sanitised on the way
    #: out (n26.core.templatetags.richtext), so a tightened allowlist
    #: reaches what was already saved.
    notes = models.TextField(blank=True, default="")
    #: The gang's story. Same treatment as notes.
    lore = models.TextField(blank=True, default="")
    #: A picture of the gang, in the site's media storage. Surfaces read
    #: its URL and never the bytes.
    image = models.ImageField(upload_to="gang-images/", blank=True, default="")

    #: What ``open_actions`` read, or None before it has. Held on the
    #: instance rather than fetched per question; see there.
    _open_actions = None

    class Meta:
        verbose_name = "gang"
        verbose_name_plural = "gangs"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def recompute_rating(self):
        """Everything the gang owns, at any depth.

        Excludes archived assignments — a sold weapon stops counting, while
        its ledger entry stays a true statement of what it was worth.
        """
        from n26.core.reconcile import sum_rating

        # The stash is excluded: rating is what the models are worth;
        # stashed gear counts in wealth instead.
        return sum_rating(gang_root=self, stash_root__isnull=True)

    def recompute_credits(self):
        """The budget less everything spent — or None where no budget is.

        With no budget there is nothing to count down from: purchases are
        honest ledger lines and the gang's number is its rating.
        """
        from n26.core.reconcile import total_spent

        if self.starting_credits is None:
            return None
        return self.starting_credits - total_spent(self)

    def repin_credits(self):
        remaining = self.recompute_credits()
        self.credits = remaining if remaining is not None else 0
        self.save(update_fields=["credits", "modified"])
        return self.credits

    @property
    def trade_points_spent(self):
        """What has gone at the post since the allowance was last set.

        Summed from the log rather than pinned, which is the whole
        difference from credits: Trade Points belong to a trip and not
        to the gang, so there is no standing figure to keep honest. A
        refund inside the same trip hands its points back.

        Asked of the database each time rather than cached on the
        instance: a page's query count is an invariant here, and a cache
        that answers the second reading for free makes the count depend
        on how many times a page happened to ask.
        """
        from n26.core.reconcile import trade_points_spent

        return trade_points_spent(self)

    def open_actions(self):
        """Every action this gang has open, by kind.

        One query for all of them, held on the instance. A page asks
        about more than one kind — the gang sheet draws the founding
        card and the visit's figure in the same breath — and asking per
        kind would cost a query each, so they are read together and the
        instance remembers.

        The opening event rides along: what a visit brought and who
        performed it are read off it, and a second query for a row
        already in hand would be a join this could have made.

        Held, where what an action has spent is not: spending moves as a
        page acts on it, and which actions are open does not. An
        operation drops what was held the moment it closes, so a page
        that opened or closed one still reads the truth.
        """
        if self._open_actions is None:
            from n26.core.models import Action

            self._open_actions = {
                action.kind: action
                for action in Action.objects.filter(
                    gang=self, closed__isnull=True
                ).select_related("opened")
            }
        return self._open_actions

    def forget_open_actions(self):
        """Drop what was read, so the next reader asks again.

        Everything held about which actions are open goes, however it
        arrived — the rows read on demand and the figure a queryset read
        with the gang's own row. Called wherever an action is opened or
        closed, and wherever a reading taken earlier must not be trusted.
        """
        self._open_actions = None
        self.__dict__.pop(_OPEN_VISIT_POINTS, None)

    def hold_open_visit(self, brought):
        """Take what a queryset read about this gang's open visit.

        For a queryset that reached the gang through something else — a
        fighter's page annotates on the fighter and hands the figure
        over here, because the gang is what draws it.
        """
        self.__dict__[_OPEN_VISIT_POINTS] = brought

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self.forget_open_actions()

    def open_action(self, kind):
        """The action of this kind the gang has open, or None.

        One row at most: the database holds a gang to one open action of
        each kind, so there is never a set to pick from.
        """
        return self.open_actions().get(kind)

    @property
    def open_visit(self):
        """The open Visit Trading Post action, or None."""
        from n26.core.models import Action

        return self.open_action(Action.Kind.TRADING_POST_VISIT)

    @property
    def open_visit_brought(self):
        """What the open Visit Trading Post action brought, or None where
        no visit is open.

        Nought is a figure and None is an absence: a visit that brought
        no points is still a visit, and the post is still open to a gang
        performing one.

        Read off the gang's own row where the queryset asked for it
        (``open_visit_points``) — a page that draws the figure and never
        acts on the visit wants no more than this, and pays for no query
        of its own. Where it did not, the action is read instead.
        """
        if _OPEN_VISIT_POINTS in self.__dict__:
            return self.__dict__[_OPEN_VISIT_POINTS]
        visit = self.open_visit
        return None if visit is None else (visit.trade_points or 0)

    @property
    def visiting_trading_post(self):
        """Whether a Visit Trading Post action is open.

        The rules only let a gang buy from the post where a fighter
        performed the action, so this is a real state and not an
        allowance of nothing: a visit that has spent every point is
        still a visit.

        It is not a gate. Nothing consults this to refuse a purchase —
        the equip screens read it to say where the gang stands, and a
        buy with no action open goes through once its question is
        answered.
        """
        return self.open_visit_brought is not None

    @property
    def trade_points_left(self):
        """What the open visit has left, or None where none is open.

        Goes negative where an owner said they meant to overspend, which
        is what the confirmation before such a purchase is for: Trade
        Points inform, and only credits are refused.
        """
        brought = self.open_visit_brought
        if brought is None:
            return None
        return brought - self.trade_points_spent

    @property
    def credits_unlimited(self):
        """Whether this gang spends against a budget at all.

        No starting credits means no ceiling: the gang buys what it likes
        and its number is its rating, so the credits figure counts
        nothing. A surface draws that as "no answer" rather than as a
        zero, which is what a gang that has spent everything shows.
        """
        return self.starting_credits is None

    @property
    def stash_rating(self):
        """What the stash holds, or 0 before one exists. Column reads."""
        stash = getattr(self, "stash", None)
        return stash.rating if stash else 0

    @property
    def wealth(self):
        """Rating, plus cash, plus what the stash holds. Column reads."""
        return self.rating + self.credits + self.stash_rating
