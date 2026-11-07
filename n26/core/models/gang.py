from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from n26.core.models.abstract import Archived, Base, Owned, Rated

#: The annotation name for the open visit's Trade Points. It differs from
#: the ``open_visit_brought`` property because annotations are set with
#: ``setattr``, which a property without a setter rejects.
_OPEN_VISIT_POINTS = "open_visit_points"


def open_visit_points(gang="pk"):
    """Build a subquery for the open Trading Post visit's allocated Trade Points.

    ``gang`` is the outer queryset's path to the gang. Coalesce inside the
    subquery so None means no open visit and zero means an open visit with
    no allocated points.
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
    #: Store editor HTML unchanged and sanitise through the richtext filter
    #: when rendering, so allowlist updates also apply to saved content.
    notes = models.TextField(blank=True, default="")
    #: The gang's story. Same treatment as notes.
    lore = models.TextField(blank=True, default="")
    #: Read the uploaded gang image through its media URL.
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
        """Sum live assignment ratings under the gang, excluding stashed equipment."""
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
        """Sum Trade Point events attributed to the open Trading Post visit.

        Refunds return points to the original purchase activity. Query on every
        access rather than caching the total, keeping reads current and page
        query counts independent of previous property access.
        """
        from n26.core.reconcile import trade_points_spent

        return trade_points_spent(self)

    def open_activities(self):
        """Load open gang activities and relevant founding and hire-time history in one query.

        Cache open activities by kind alongside the first completed founding,
        latest founding and each model's latest hire-time activity. Join boundary
        events for their recorded figures and dates.

        Operations invalidate the cache at entry and settlement; activity opening
        and closing also invalidate it. Spending totals are queried separately.
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
        """Clear cached activities, activity history and the annotated open-visit allocation."""
        self._open_activities = None
        self._activity_history = None
        self.__dict__.pop(_OPEN_VISIT_POINTS, None)

    def hold_open_visit(self, brought):
        """Cache an open-visit allocation annotated on another model for the gang display."""
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
        """Return the latest founding activity, which a correction must identify before reopening."""
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
        """Return the open visit's allocated Trade Points, or None when no visit is open.

        An allocation of zero still represents an open visit. Use the queryset
        annotation when present; otherwise load the activity.
        """
        if _OPEN_VISIT_POINTS in self.__dict__:
            return self.__dict__[_OPEN_VISIT_POINTS]
        visit = self.open_visit
        return None if visit is None else (visit.trade_points or 0)

    @property
    def visiting_trading_post(self):
        """Whether a Trading Post visit is open, including visits with no points.

        This is display state. Purchase views can accept a purchase without an
        open visit after confirmation.
        """
        return self.open_visit_brought is not None

    @property
    def trade_points_left(self):
        """Return the open visit's remaining Trade Points, or None without a visit.

        The balance can be negative after a confirmed overspend.
        """
        brought = self.open_visit_brought
        if brought is None:
            return None
        return brought - self.trade_points_spent

    @property
    def credits_unlimited(self):
        """Whether the gang has no budget and pages should omit its pinned credits figure."""
        return self.starting_credits is None

    @property
    def stash_rating(self):
        stash = getattr(self, "stash", None)
        return stash.rating if stash else 0

    @property
    def wealth(self):
        return self.rating + self.credits + self.stash_rating
