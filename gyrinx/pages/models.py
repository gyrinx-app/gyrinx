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
