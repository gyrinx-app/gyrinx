"""
Background tasks with Google Cloud Pub/Sub.

This module provides background task processing using Django 6.0's native
task framework with Google Cloud Pub/Sub as the production backend.

Usage:
    1. Define tasks using Django's @task decorator in your app
    2. Register them explicitly in gyrinx/tasks/registry.py
    3. Enqueue with task.enqueue(...)

Example:
    # In gyrinx/core/tasks.py
    from django.tasks import task

    @task
    def send_welcome_email(user_id: int):
        user = User.objects.get(id=user_id)
        send_mail(...)

    # In gyrinx/tasks/registry.py
    from gyrinx.tasks import TaskRoute
    from gyrinx.core.tasks import send_welcome_email

    tasks = [
        TaskRoute(send_welcome_email),
    ]

    # Enqueue from anywhere
    send_welcome_email.enqueue(user_id=user.id)
"""

from gyrinx.tasks.route import TaskRoute

__all__ = ["TaskRoute"]
