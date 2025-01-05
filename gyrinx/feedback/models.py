from django.db import models

from gyrinx.models import Base


class Feedback(Base):
    user = models.ForeignKey(
        "auth.User", on_delete=models.DO_NOTHING, null=True, blank=False
    )

    feedback = models.TextField()

    FEEDBACK_CHOICES = [
        ("BUG", "Bug"),
        ("IDEA", "Idea"),
        ("REQUEST", "Request"),
        ("HELP", "Help"),
    ]

    feedback_type = models.CharField(
        max_length=10,
        choices=FEEDBACK_CHOICES,
        default="BUG",
    )
