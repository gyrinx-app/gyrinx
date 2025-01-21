import uuid

from django.contrib.auth.models import Group
from django.contrib.flatpages.models import FlatPage
from django.db import models
from simple_history.models import HistoricalRecords

from gyrinx.models import Base


class FlatPageVisibility(Base):
    """
    FlatPageVisibility dictates which Groups can view a FlatPage.
    """

    page = models.ForeignKey(FlatPage, on_delete=models.CASCADE)
    groups = models.ManyToManyField(
        Group,
        verbose_name="Visible to Groups",
        help_text="Select the groups that can view this page. If no groups are selected, the page is public.",
    )

    history = HistoricalRecords()

    help_text = "Select the groups that can view this page. If no groups are selected, the page is public."

    class Meta:
        verbose_name = "flat page visibility rule"
        verbose_name_plural = "flat page visibility rules"


class WaitingListSkill(Base):
    """
    WaitingListSkill is a list of skills that users can select from when signing up for the waiting list.
    """

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "waiting list skill"
        verbose_name_plural = "waiting list skills"

    def __str__(self):
        return self.name


class WaitingListEntry(Base):
    """
    WaitingList is a list of users waiting for access to the site.
    """

    email = models.EmailField(unique=True)
    desired_username = models.CharField(max_length=150, blank=True)
    yaktribe_username = models.CharField(max_length=150, blank=True)
    skills = models.ManyToManyField(
        WaitingListSkill, blank=True, related_name="waiting_list_entries"
    )
    notes = models.TextField(blank=True)
    share_code = models.UUIDField(default=uuid.uuid4, editable=False)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "waiting list entry"
        verbose_name_plural = "waiting list entries"
