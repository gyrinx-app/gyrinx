import json
import logging
from collections import defaultdict
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from gyrinx.analytics.models import Event
from gyrinx.analytics.nouns import Edition
from gyrinx.analytics.registry import growth_series

User = get_user_model()
logger = logging.getLogger(__name__)


class AnalyticsAdminSite(admin.site.__class__):
    """Custom admin site with analytics dashboard.

    Extends whatever class ``admin.site`` is currently using rather than
    ``admin.AdminSite`` directly, so it composes with the site installed by
    ``gyrinx.admin_site`` (which routes admin login through allauth) instead of
    replacing it. ``gyrinx.maintenance`` then stacks on top of this — see
    ``gyrinx/maintenance/admin.py``.
    """

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "analytics/dashboard/",
                self.admin_view(self.analytics_dashboard_view),
                name="analytics_dashboard",
            ),
        ]
        return custom_urls + urls

    def analytics_dashboard_view(self, request):
        """Main analytics dashboard view"""
        time_scale = request.GET.get("time_scale", "30d")

        # Parse time scale
        scale_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365,
        }
        days = scale_map.get(time_scale, 30)
        start_date = timezone.now() - timedelta(days=days)

        # Which product to look at. Two editions run side by side, so their
        # activity has to be readable apart: added together, one growing while
        # the other shrinks looks like a flat site. An unrecognised value falls
        # back to showing everything.
        wanted = request.GET.get("edition", "")
        edition = wanted if wanted in Edition.values else None

        # Get data for hard-coded graphs
        user_data = self.get_user_registration_data(start_date)
        events_data = self.get_top_events_data(start_date, edition)
        cumulative_data = self.get_cumulative_creation_data(start_date, edition)

        context = {
            **self.each_context(request),
            "title": "Analytics Dashboard",
            "time_scale": time_scale,
            "edition": edition or "",
            "editions": [{"value": "", "label": "All editions"}]
            + [{"value": e.value, "label": e.label} for e in Edition],
            "time_scales": [
                {"value": "7d", "label": "Last 7 Days"},
                {"value": "30d", "label": "Last 30 Days"},
                {"value": "90d", "label": "Last 90 Days"},
                {"value": "1y", "label": "Last Year"},
            ],
            "user_data": json.dumps(user_data),
            "events_data": json.dumps(events_data),
            "cumulative_data": json.dumps(cumulative_data),
        }

        return render(request, "analytics/admin/dashboard.html", context)

    def get_user_registration_data(self, start_date):
        """Get user registration data.

        Not narrowed by the edition filter: an account is the site's, and the
        same sign-up reaches both editions.
        """
        # Get daily user counts
        daily_users = (
            User.objects.filter(date_joined__gte=start_date)
            .annotate(date=TruncDate("date_joined"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Create a dictionary of dates with counts
        user_counts = {entry["date"]: entry["count"] for entry in daily_users}

        # Generate all dates in the range
        current_date = start_date.date()
        end_date = timezone.now().date()
        labels = []
        data = []

        while current_date <= end_date:
            labels.append(current_date.strftime("%Y-%m-%d"))
            data.append(user_counts.get(current_date, 0))
            current_date += timedelta(days=1)

        return {
            "labels": labels,
            "data": data,
        }

    def get_top_events_data(self, start_date, edition=None):
        """Get top events excluding views.

        A noun belongs to one edition, so the lines never merge two products
        into one; the filter is there to stop one edition's busiest actions
        crowding the other's out of the top ten.
        """
        events = Event.objects.all()
        if edition is not None:
            events = events.filter(edition=edition)

        # First get top 10 event types
        top_event_types = (
            events.filter(created__gte=start_date)
            .exclude(verb="view")
            .values("noun", "verb")
            .annotate(total=Count("id"))
            .order_by("-total")[:10]
        )

        # Create a list of (noun, verb) tuples for the top events
        top_events = [(item["noun"], item["verb"]) for item in top_event_types]

        # Get daily counts for these top events
        daily_events = (
            events.filter(
                created__gte=start_date,
                noun__in=[e[0] for e in top_events],
                verb__in=[e[1] for e in top_events],
            )
            .annotate(date=TruncDate("created"))
            .values("date", "noun", "verb")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Group by event type
        series_data = defaultdict(lambda: defaultdict(int))

        for entry in daily_events:
            event_type = f"{entry['noun']} - {entry['verb']}"
            # Only include if it's one of our top events
            if (entry["noun"], entry["verb"]) in top_events:
                series_data[event_type][entry["date"]] = entry["count"]

        # Generate all dates in the range
        current_date = start_date.date()
        end_date = timezone.now().date()
        all_dates = []

        while current_date <= end_date:
            all_dates.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        # Convert to Chart.js format
        datasets = []
        colors = [
            {"border": "rgb(255, 99, 132)", "background": "rgba(255, 99, 132, 0.2)"},
            {"border": "rgb(54, 162, 235)", "background": "rgba(54, 162, 235, 0.2)"},
            {"border": "rgb(255, 206, 86)", "background": "rgba(255, 206, 86, 0.2)"},
            {"border": "rgb(75, 192, 192)", "background": "rgba(75, 192, 192, 0.2)"},
            {"border": "rgb(153, 102, 255)", "background": "rgba(153, 102, 255, 0.2)"},
            {"border": "rgb(255, 159, 64)", "background": "rgba(255, 159, 64, 0.2)"},
            {"border": "rgb(199, 199, 199)", "background": "rgba(199, 199, 199, 0.2)"},
            {"border": "rgb(83, 102, 255)", "background": "rgba(83, 102, 255, 0.2)"},
            {"border": "rgb(255, 99, 255)", "background": "rgba(255, 99, 255, 0.2)"},
            {"border": "rgb(99, 255, 132)", "background": "rgba(99, 255, 132, 0.2)"},
        ]

        for i, (event_type, date_data) in enumerate(series_data.items()):
            series_values = []
            for date_str in all_dates:
                # Convert date string back to date object for lookup
                date_obj = timezone.datetime.strptime(date_str, "%Y-%m-%d").date()
                series_values.append(date_data.get(date_obj, 0))

            datasets.append(
                {
                    "label": event_type,
                    "data": series_values,
                    "borderColor": colors[i % len(colors)]["border"],
                    "backgroundColor": colors[i % len(colors)]["background"],
                    "tension": 0.1,
                }
            )

        return {
            "labels": all_dates,
            "datasets": datasets,
        }

    def get_cumulative_creation_data(self, start_date, edition=None):
        """Cumulative creation counts, one line per registered growth series.

        What gets counted is the edition's business — the platform only knows
        how to accumulate. See ``gyrinx.analytics.registry``; with nothing
        registered the chart renders empty rather than failing.

        Every line says which edition it belongs to, so picking one leaves
        only that product's lines. Nothing is summed across editions here:
        each line stays its own.
        """
        series = growth_series(edition)
        counts_by_series = [s.daily_counts(start_date) for s in series]

        datasets = [
            {
                "label": s.label,
                "data": [],
                "borderColor": s.border_color,
                "backgroundColor": s.background_color,
                "tension": 0.1,
            }
            for s in series
        ]

        # Generate all dates in the range
        current_date = start_date.date()
        end_date = timezone.now().date()

        labels = []
        running_totals = [0] * len(series)

        while current_date <= end_date:
            labels.append(current_date.strftime("%Y-%m-%d"))
            for i, counts in enumerate(counts_by_series):
                running_totals[i] += counts.get(current_date, 0)
                datasets[i]["data"].append(running_totals[i])

            current_date += timedelta(days=1)

        return {
            "labels": labels,
            "datasets": datasets,
        }


# Override the default admin site
admin.site.__class__ = AnalyticsAdminSite
