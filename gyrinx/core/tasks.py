import logging

from django.tasks import task

logger = logging.getLogger(__name__)


@task
def hello_world(name: str = "World"):
    """Demo task for testing the task framework."""
    logger.info(f"Hello, {name}!")
    return f"Greeted {name}"


@task
def refresh_list_facts(list_id: str):
    """
    Refresh the cached facts for a list by recalculating from database.

    Called asynchronously when facts_with_fallback detects a dirty cache.
    """
    from gyrinx.core.models import List

    try:
        lst = List.objects.with_related_data(with_fighters=True).get(pk=list_id)
        lst.facts_from_db(update=True)
        logger.info(f"Refreshed facts for list {list_id}")
    except List.DoesNotExist:
        logger.warning(f"List {list_id} not found for facts refresh")
