"""Routes for Pub/Sub push delivery and public task-group progress."""

from django.urls import path

from gyrinx.tasks.views import pubsub_push_handler, task_group_status

app_name = "tasks"

urlpatterns = [
    path("pubsub/", pubsub_push_handler, name="pubsub"),
    path("status", task_group_status, name="group-status"),
]
