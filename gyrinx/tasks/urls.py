"""
URL configuration for tasks app.

The single endpoint receives all Pub/Sub push messages. Routing to specific
task handlers is done by the view based on the task_name in the payload.
"""

from django.urls import path

from gyrinx.tasks.views import pubsub_push_handler

app_name = "tasks"

urlpatterns = [
    path("pubsub/", pubsub_push_handler, name="pubsub"),
]
