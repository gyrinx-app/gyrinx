from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from n26.core.models.abstract import Archived, Base, Owned, Rated

#: The annotation name for the open visit's Trade Points. It differs from
#: the ``open_visit_brought`` property because annotations are set with
#: ``setattr``, which a property without a setter rejects.
_OPEN_VISIT_POINTS = "open_visit_points"


def open_visit_points(gang="pk"):
    """A subquery for the Trade Points the gang's open Visit Trading Post
    activity brought, for annotating a queryset.

    ``gang`` is the path from the queryset's model to the gang, so a
    fighter queryset can annotate its gang's figure.

    The figure is coalesced inside the subquery, so null means no open
    visit and 0 means a visit that brought no points.
    """
    from n26.core.models import Activity

    return Subquery(
        Activity.objects.filter(
            gang=OuterRef(gang),
            kind=Activity.Kind.TRADING_POST_VISIT,
            closed__isnull=True,
        )
        .annotate(brought=Coalesce("trade_points", Value(0)))
        .values("brought")[:1]
    )


class Gang(Base, Owned, Archived, Rated):
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

    #: Cache for ``open_activities``; None until it runs.
    _open_activities = None
    _activity_history = None

    class Meta:
        verbose_name = "gang"
        verbose_name_plural = "gangs"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def recompute_rating(self):
        """The rating of everything the gang owns, at any depth.

        Archived assignments are excluded: a sold weapon stops counting,
        but its ledger entry keeps the value it had.
        """
        from n26.core.reconcile import sum_rating

        # The stash is excluded: rating is what the models are worth;
        # stashed gear counts in wealth instead.
        return sum_rating(gang_root=self, stash_root__isnull=True)

    def recompute_credits(self):
        """The budget less everything spent, or None when there is no budget.

        Without a budget, purchases are still recorded in the ledger and the
        gang is measured by its rating.
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
        """Trade Points the open Visit Trading Post activity has spent.

        Summed from the ledger, not pinned like credits: Trade Points
        belong to one visit, not to the gang, so there is no standing total
        to keep. A refund during the visit returns its points.

        Queried every time, not cached on the instance. Page query counts
        are fixed and tested, and a cache would make the count depend on
        how many times a page reads this.
        """
        from n26.core.reconcile import trade_points_spent

        return trade_points_spent(self)

    def open_activities(self):
        """Open gang activities by kind, cached on the instance.

        One query loads the open activities, the first completed founding,
        the latest founding activity and each model's latest hire-time
        activity. Pages need several kinds at once (the gang sheet shows the
        founding card and the visit's figure together), so one query
        replaces one per kind.

        The opening and closing events are joined in, because a visit's
        Trade Points and its visitors are read from the opening event.

        This is cached and ``trade_points_spent`` is not: spending changes
        as a page acts, but which activities are open changes only when one
        opens or closes. Every operation clears this cache when it starts
        and when it settles, as do opening and closing an activity, so a
        page reads current state afterwards.
        """
        if self._open_activities is None:
            from django.db.models import Q, Subquery

            from n26.core.models import Activity

            history = Activity.objects.filter(gang=self)
            boundary = (
                history.filter(kind=Activity.Kind.FOUNDING, closed__isnull=False)
                .order_by("closed__created", "pk")
                .values("pk")[:1]
            )
            latest_founding = (
                history.filter(kind=Activity.Kind.FOUNDING)
                .order_by("-created", "-pk")
                .values("pk")[:1]
            )
            latest = (
                history.filter(kind=Activity.Kind.HIRE_TIME)
                .order_by("miniature_id", "-created", "-pk")
                .distinct("miniature_id")
                .values("pk")
            )
            self._activity_history = list(
                history.filter(
                    Q(closed__isnull=True)
                    | Q(pk=Subquery(boundary))
                    | Q(pk=Subquery(latest_founding))
                    | Q(pk__in=Subquery(latest))
                )
                .select_related("opened", "closed")
                .order_by("created", "pk")
            )
            self._open_activities = {
                activity.kind: activity
                for activity in self._activity_history
                if activity.closed_id is None and activity.miniature_id is None
            }
        return self._open_activities

    def forget_open_activities(self):
        """Clear every cached read about open activities.

        That covers the activities ``open_activities`` loaded and any
        ``open_visit_points`` annotation. Call it wherever an activity opens
        or closes, or wherever an earlier read may be stale.
        """
        self._open_activities = None
        self._activity_history = None
        self.__dict__.pop(_OPEN_VISIT_POINTS, None)

    def hold_open_visit(self, brought):
        """Store an ``open_visit_points`` value annotated on another model.

        A fighter page annotates the figure on the fighter and passes it
        here, because the gang renders it.
        """
        self.__dict__[_OPEN_VISIT_POINTS] = brought

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self.forget_open_activities()

    def open_activity(self, kind, miniature=None):
        if miniature is not None:
            self.open_activities()
            return next(
                (
                    a
                    for a in self._activity_history
                    if a.kind == kind and a.miniature_id == miniature.pk and a.is_open
                ),
                None,
            )
        return self.open_activities().get(kind)

    def founding_completed_at(self):
        """When founding was first completed: the recruitment boundary."""
        from n26.core.models import Activity

        self.open_activities()
        return min(
            (
                a.closed.created
                for a in self._activity_history
                if a.kind == Activity.Kind.FOUNDING and a.closed_id
            ),
            default=None,
        )

    def latest_founding_activity(self):
        """The latest founding activity, which a founding correction must
        name before reopening it."""
        from n26.core.models import Activity

        self.open_activities()
        return next(
            (
                a
                for a in reversed(self._activity_history)
                if a.kind == Activity.Kind.FOUNDING
            ),
            None,
        )

    def hire_time_activities(self):
        """Each model's latest hire-time activity, loaded together for the roster."""
        from n26.core.models import Activity

        self.open_activities()
        return {
            a.miniature_id: a
            for a in self._activity_history
            if a.kind == Activity.Kind.HIRE_TIME
        }

    @property
    def open_visit(self):
        from n26.core.models import Activity

        return self.open_activity(Activity.Kind.TRADING_POST_VISIT)

    @property
    def open_visit_brought(self):
        """Trade Points the open Visit Trading Post activity brought, or None
        when no visit is open.

        0 is a real value: a visit that brought no points is still open,
        and the gang can still buy at the Trading Post.

        Uses the ``open_visit_points`` annotation when the queryset added
        it, so a page that only shows the figure needs no extra query.
        Otherwise it reads the activity.
        """
        if _OPEN_VISIT_POINTS in self.__dict__:
            return self.__dict__[_OPEN_VISIT_POINTS]
        visit = self.open_visit
        return None if visit is None else (visit.trade_points or 0)

    @property
    def visiting_trading_post(self):
        """Whether a Visit Trading Post activity is open.

        The rules let a gang buy at the Trading Post only while a fighter
        is visiting it, so an open visit with no points left still counts.

        Nothing refuses a purchase on this. The equip pages read it to show
        the gang's state, and a purchase with no activity open goes ahead
        once the owner confirms it.
        """
        return self.open_visit_brought is not None

    @property
    def trade_points_left(self):
        """Trade Points the open visit has left, or None when no visit is open.

        Goes negative when an owner confirms an overspend. Overspending
        Trade Points is allowed after a confirmation; only overspending
        credits is refused.
        """
        brought = self.open_visit_brought
        if brought is None:
            return None
        return brought - self.trade_points_spent

    @property
    def credits_unlimited(self):
        """Whether the gang has no budget.

        Without starting credits the gang buys freely and is measured by
        its rating, so ``credits`` means nothing. Pages show no credits
        figure instead of 0, which would read as a gang that has spent
        everything.
        """
        return self.starting_credits is None

    @property
    def stash_rating(self):
        stash = getattr(self, "stash", None)
        return stash.rating if stash else 0

    @property
    def wealth(self):
        return self.rating + self.credits + self.stash_rating
