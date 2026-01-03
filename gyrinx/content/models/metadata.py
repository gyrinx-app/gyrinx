"""
Metadata models for content data.

This module contains:
- ContentRule: Game rules
- ContentBook: Rulebooks
- ContentPolicy: Equipment policies (legacy/unused)
- ContentPageRef: Page references to rulebooks
"""

from difflib import SequenceMatcher

from django.core.cache import caches
from django.db import models
from django.db.models import Case, Q, When
from django.db.models.functions import Cast
from django.utils.functional import cached_property
from simple_history.models import HistoricalRecords

from .base import Content


def similar(a, b):
    """
    Returns a similarity ratio between two strings, ignoring case.
    If one is contained in the other, returns 0.9 for partial matches,
    or 1.0 if they are identical.
    """
    lower_a = a.lower()
    lower_b = b.lower()
    if lower_a == lower_b:
        return 1.0
    if lower_a in lower_b or lower_b in lower_a:
        return 0.9
    return SequenceMatcher(None, a, b).ratio()


class ContentRule(Content):
    """
    Represents a specific rule from the game system.
    """

    name = models.CharField(max_length=255)

    history = HistoricalRecords()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Rule"
        verbose_name_plural = "Rules"
        ordering = ["name"]


class ContentBook(Content):
    """
    Represents a rulebook, including its name, shortname, year of publication,
    and whether it is obsolete.
    """

    help_text = "Captures rulebook information."
    name = models.CharField(max_length=255)
    shortname = models.CharField(max_length=50, blank=True, null=False)
    year = models.CharField(blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    type = models.CharField(max_length=50, blank=True, null=False)
    obsolete = models.BooleanField(default=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.name} ({self.type}, {self.year})"

    class Meta:
        verbose_name = "Book"
        verbose_name_plural = "Books"
        ordering = ["name"]


class ContentPolicy(Content):
    """
    Captures rules for restricting or allowing certain equipment to fighters.
    """

    help_text = (
        "Not used currently. Captures the rules for equipment availability to fighters."
    )
    fighter = models.ForeignKey(
        "ContentFighter", on_delete=models.CASCADE, db_index=True
    )
    rules = models.JSONField()
    history = HistoricalRecords()

    def allows(self, equipment) -> bool:
        """
        Determines if the equipment is allowed by the policy. This is evaluated
        by checking rules from last to first.
        """
        name = equipment.name
        # TODO: This won't work - this model should be dropped for now as it's not used
        #       and is deadwood.
        category = equipment.category.name

        def check(rule_item, category, name):
            """Check if a rule item matches the category and name."""
            rule_category = rule_item.get("category")
            rule_name = rule_item.get("name")
            if rule_category and rule_category != category:
                return False
            if rule_name and rule_name != name:
                return False
            return True

        # Work through the rules in reverse order. If any of them
        # allow, then the equipment is allowed.
        # If we get to an explicit deny, then the equipment is denied.
        # If we get to the end, then the equipment is allowed.
        for rule in reversed(self.rules):
            deny = rule.get("deny", [])
            if deny == "all":
                return False
            # The deny rule is an AND rule. The category and name must
            # both match, or be missing, for the rule to apply.
            deny_fail = any([check(d, category, name) for d in deny])
            if deny_fail:
                return False

            allow = rule.get("allow", [])
            if allow == "all":
                return True
            # The allow rule is an AND rule. The category and name must
            # both match, or be missing, for the allow to apply.
            allow_pass = any([check(a, category, name) for a in allow])
            if allow_pass:
                return True

        return True

    class Meta:
        verbose_name = "Policy"
        verbose_name_plural = "Policies"


class ContentPageRef(Content):
    """
    Represents a reference to a page (or pages) in a rulebook (:model:`content.ContentBook`). Provides a parent
    relationship for nested references, used to resolve page numbers.
    """

    help_text = "Captures the page references for game content. Title is used to match with other entities (e.g. Skills)."
    book = models.ForeignKey(ContentBook, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    page = models.CharField(max_length=50, blank=True, null=False)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    category = models.CharField(max_length=255, blank=True, null=False)
    description = models.TextField(blank=True, null=False)
    history = HistoricalRecords()

    def __str__(self):
        return f"{self.book.shortname} - {self.category} - p{self.resolve_page_cached} - {self.title}".strip()

    def bookref(self):
        """
        Returns a short, human-readable reference string combining the
        book shortname and resolved page number.
        """
        return f"{self.book.shortname} p{self.resolve_page_cached}".strip()

    def resolve_page(self):
        """
        If the page field is empty, attempts to resolve the page
        through its parent. Returns None if no page can be resolved.
        """
        if self.page:
            return self.page

        if self.parent:
            return self.parent.resolve_page_cached

        return None

    @cached_property
    def resolve_page_cached(self):
        return self.resolve_page()

    class Meta:
        verbose_name = "Page Reference"
        verbose_name_plural = "Page References"
        ordering = ["category", "book__name", "title"]

    # TODO: Move this to a custom Manager
    @classmethod
    def find(cls, *args, **kwargs):
        """
        Finds a single page reference matching the given query parameters.
        Returns the first match or None if no match is found.
        """
        return ContentPageRef.objects.filter(*args, **kwargs).first()

    # TODO: Move this to a custom Manager
    @classmethod
    def find_similar(cls, title: str, **kwargs):
        """
        Finds references whose titles match or are similar to the given string.
        Uses caching to avoid repeated lookups. Returns a QuerySet.
        """
        cache = caches["content_page_ref_cache"]
        key = f"content_page_ref_cache:{title}"
        cached = cache.get(key)
        if cached:
            return cached

        refs = ContentPageRef.objects.filter(**kwargs).filter(
            Q(title__icontains=title) | Q(title=title)
        )
        cache.set(key, refs)
        return refs

    # TODO: Move this to a custom Manager
    @classmethod
    def all_ordered(cls):
        """
        Returns top-level page references (no parent) with numeric pages, ordered by:
        - Core book first
        - Then by book shortname
        - Then ascending by numeric page
        """
        return (
            # TODO: Implement this as a method on the Manager/QuerySet
            ContentPageRef.objects.filter(parent__isnull=True)
            .exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
            )
        )

    # TODO: Add default ordering to the Meta class, possibly with default annotations from the Manager
    def children_ordered(self):
        """
        Returns any child references of this reference that have a page specified,
        ordered similarly (Core first, then shortname, then ascending page, then title).
        """
        return (
            self.children.exclude(page="")
            .annotate(page_int=Cast("page", models.IntegerField(null=True, blank=True)))
            .order_by(
                Case(
                    When(book__shortname="Core", then=0),
                    default=99,
                ),
                "book__shortname",
                "page_int",
                "title",
            )
        )

    def children_no_page(self):
        """
        Returns any child references of this reference that do not have a page
        specified, ordered similarly (Core first, then shortname, then title).
        """
        return self.children.filter(page="").order_by(
            Case(
                When(book__shortname="Core", then=0),
                default=99,
            ),
            "book__shortname",
            "title",
        )
