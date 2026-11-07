"""Django tasks with Pub/Sub production delivery and a local durable backend.

Define @task functions in an app's tasks.py and export a TaskRoute for
each in task_routes. Discovery collects those declarations; callers enqueue
through task.enqueue(...). See gyrinx/tasks/discovery.py.
"""

from gyrinx.tasks.route import PausedTaskConsumer, TaskRoute

__all__ = ["PausedTaskConsumer", "TaskRoute"]
