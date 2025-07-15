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

from gyrinx.core.models import Campaign, Event, List, ListFighter

User = get_user_model()
logger = logging.getLogger(__name__)


class AnalyticsAdminSite(admin.AdminSite):
    """Custom admin site with analytics dashboard"""

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

        # Get data for hard-coded graphs
        user_data = self.get_user_registration_data(start_date)
        events_data = self.get_top_events_data(start_date)
        cumulative_data = self.get_cumulative_creation_data(start_date)

        context = {
            **self.each_context(request),
            "title": "Analytics Dashboard",
            "time_scale": time_scale,
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
        """Get user registration data"""
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

    def get_top_events_data(self, start_date):
        """Get top events excluding views"""
        # First get top 10 event types
        top_event_types = (
            Event.objects.filter(created__gte=start_date)
            .exclude(verb="view")
            .values("noun", "verb")
            .annotate(total=Count("id"))
            .order_by("-total")[:10]
        )

        # Create a list of (noun, verb) tuples for the top events
        top_events = [(item["noun"], item["verb"]) for item in top_event_types]

        # Get daily counts for these top events
        daily_events = (
            Event.objects.filter(
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

    def get_cumulative_creation_data(self, start_date):
        """Get cumulative creation data for fighters, lists, and campaigns"""
        # Get daily counts for fighters in list-building lists
        daily_fighters = (
            ListFighter.objects.filter(
                created__gte=start_date, list__status=List.LIST_BUILDING
            )
            .annotate(date=TruncDate("created"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Get daily counts for list-building lists
        daily_lists = (
            List.objects.filter(created__gte=start_date, status=List.LIST_BUILDING)
            .annotate(date=TruncDate("created"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Get daily counts for campaigns
        daily_campaigns = (
            Campaign.objects.filter(created__gte=start_date)
            .annotate(date=TruncDate("created"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("date")
        )

        # Create dictionaries for quick lookup
        fighter_counts = {entry["date"]: entry["count"] for entry in daily_fighters}
        list_counts = {entry["date"]: entry["count"] for entry in daily_lists}
        campaign_counts = {entry["date"]: entry["count"] for entry in daily_campaigns}

        # Generate all dates in the range
        current_date = start_date.date()
        end_date = timezone.now().date()

        labels = []
        datasets = [
            {
                "label": "Fighters (Cumulative)",
                "data": [],
                "borderColor": "rgb(75, 192, 192)",
                "backgroundColor": "rgba(75, 192, 192, 0.2)",
                "tension": 0.1,
            },
            {
                "label": "Lists (Cumulative)",
                "data": [],
                "borderColor": "rgb(54, 162, 235)",
                "backgroundColor": "rgba(54, 162, 235, 0.2)",
                "tension": 0.1,
            },
            {
                "label": "Campaigns (Cumulative)",
                "data": [],
                "borderColor": "rgb(255, 99, 132)",
                "backgroundColor": "rgba(255, 99, 132, 0.2)",
                "tension": 0.1,
            },
        ]

        cumulative_fighters = 0
        cumulative_lists = 0
        cumulative_campaigns = 0

        while current_date <= end_date:
            # Add daily counts to cumulative totals
            cumulative_fighters += fighter_counts.get(current_date, 0)
            cumulative_lists += list_counts.get(current_date, 0)
            cumulative_campaigns += campaign_counts.get(current_date, 0)

            labels.append(current_date.strftime("%Y-%m-%d"))
            datasets[0]["data"].append(cumulative_fighters)
            datasets[1]["data"].append(cumulative_lists)
            datasets[2]["data"].append(cumulative_campaigns)

            current_date += timedelta(days=1)

        return {
            "labels": labels,
            "datasets": datasets,
        }


# Override the default admin site
admin.site.__class__ = AnalyticsAdminSite
