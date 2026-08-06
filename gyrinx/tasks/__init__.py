"""
Background tasks with Google Cloud Pub/Sub.

This module provides background task processing using Django 6.0's native
task framework with Google Cloud Pub/Sub as the production backend.

Usage:
    1. Define tasks using Django's @task decorator in your app's tasks.py
    2. Declare a TaskRoute for each in that module's `task_routes` list
    3. Enqueue with task.enqueue(...)

The platform discovers `task_routes` from every installed app, so registering a
task never means editing platform code (see gyrinx/tasks/discovery.py).

Example:
    # In n23/core/tasks.py — declaration and route in one file
    from django.tasks import task

    from gyrinx.tasks import TaskRoute

    @task
    def send_welcome_email(user_id: int):
        user = User.objects.get(id=user_id)
        send_mail(...)

    task_routes = [
        TaskRoute(send_welcome_email),
    ]

    # Enqueue from anywhere
    send_welcome_email.enqueue(user_id=user.id)
"""

from gyrinx.tasks.route import TaskRoute

__all__ = ["TaskRoute"]
