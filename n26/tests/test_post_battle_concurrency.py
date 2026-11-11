"""Concurrent command copies acknowledge one durable draft mutation."""

import pytest
from django.contrib.auth.models import User

from n26.core.models import PostBattleReport
from n26.tests.test_views_post_battle import (
    _seed_report_catalogue,
)
from n26.tests.test_views_post_battle import (
    gang_type as gang_type,
)
from n26.tests.test_views_post_battle import (
    person_statline_type as person_statline_type,
)
from n26.tests.test_views_post_battle import (
    person_type as person_type,
)
from n26.tests.test_views_post_battle import (
    table as table,
)
from n26.tests.test_views_post_battle_react import command_page


@pytest.fixture
def _prepared_report_catalogue(db):
    # The view suite's module transaction intentionally hides content from other
    # connections. This test needs committed fixture data for both contenders.
    _seed_report_catalogue()


@pytest.mark.django_db(transaction=True)
def test_concurrent_draft_retries_acknowledge_one_saved_revision(client, table):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections
    from django.http import QueryDict

    from n26.core.models.post_battle import PostBattleCommandReceipt
    from n26.core.post_battle_workflow import command

    report, data = command_page(client, table)
    posted = QueryDict(mutable=True)
    for name, values in data.items():
        posted.setlist(name, values if isinstance(values, list) else [str(values)])
    ready = Barrier(2)

    def submit(_):
        close_old_connections()
        try:
            fresh = PostBattleReport.objects.select_related("gang", "battle").get(
                pk=report.pk
            )
            actor = User.objects.get(pk=table.owner.pk)
            ready.wait(timeout=10)
            return command(fresh, actor, posted)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(result.replayed for result in results) == [False, True]
    assert results[0].acknowledged == results[1].acknowledged
    report.refresh_from_db()
    assert report.draft_revision == 1
    assert PostBattleCommandReceipt.objects.filter(report=report).count() == 1
