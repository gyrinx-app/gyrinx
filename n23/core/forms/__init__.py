"""Edition form helpers.

Bootstrap widgets moved to ``gyrinx.widgets``; the allauth and username forms to
``gyrinx.account_forms``. ``BadgeSelectionForm`` stays until ``UserProfile`` is a
platform model.
"""

from django import forms

from gyrinx.badges import HIDE_BADGE, badge_choices
from gyrinx.widgets import BsRadioSelect


class BadgeSelectionForm(forms.Form):
    """Let a user choose which badge to display.

    The available choices are every badge the user can display (see
    ``UserProfile.available_badges`` — Patreon tiers plus staff) plus an explicit
    "Hide badge" option. Eligible users show a badge by default, so the form
    pre-selects whatever is actually displayed. ``clean_selected_badge`` re-checks
    eligibility to reject tampered submissions.
    """

    selected_badge = forms.ChoiceField(
        required=False,
        label="Badge",
        widget=BsRadioSelect,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.profile = self.user.profile
        self.fields["selected_badge"].choices = badge_choices(
            self.profile.available_badges
        )
        # Pre-select whatever the profile actually displays: an explicit
        # still-eligible pick, the opt-out, or the highest-ranked default.
        if self.profile.selected_badge == HIDE_BADGE:
            initial = HIDE_BADGE
        else:
            displayed = self.profile.display_badge
            initial = displayed.slug if displayed else HIDE_BADGE
        self.fields["selected_badge"].initial = initial

    def clean_selected_badge(self):
        value = self.cleaned_data.get("selected_badge", "")
        if value in ("", HIDE_BADGE):
            return value
        if value not in self.profile.eligible_badge_slugs:
            raise forms.ValidationError("That badge isn't available to you.")
        return value

    def save(self):
        """Persist the selected badge to the user's profile."""
        self.profile.selected_badge = self.cleaned_data["selected_badge"]
        self.profile.save(update_fields=["selected_badge"])
        return self.profile
