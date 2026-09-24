"""The shared changelog, mounted by the platform at /changelog/.

The edition's own /n26/changelog/ addresses redirect here. Keeping the
patterns in this module lets the platform include them without importing
the edition's view package.
"""

from django.urls import path

from n26.core.views.changelog import changelog, changelog_entry

urlpatterns = [
    path("", changelog, name="changelog"),
    path("<uuid:pk>/", changelog_entry, name="changelog-entry"),
]
