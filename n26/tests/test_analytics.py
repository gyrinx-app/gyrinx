"""What this edition records, and what happens when recording goes wrong.

A seam test: the events table is the platform's, and this is the one place
n26 reaches into it. The claim worth pinning is not that a row appears — it is
that the row says *gang*, and says *n26*, so nobody reading the dashboard
mistakes a gang founded here for a list built next door.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.analytics.models import Event
from n26.analytics import N26Noun
from n26.core.models import Gang
from n26.library.models import GangType

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang_type(db):
    return GangType.objects.create(name="Goliath", starting_credits=1000)


def found_one(client, gang_type, name="Rust in Peace", headers=None):
    return client.post(
        reverse("n26-create-gang"),
        {
            "name": name,
            "gang_type": str(gang_type.pk),
            "starting_credits": "",
            "colour": "",
        },
        headers=headers,
    )


class TestASpeculativeFetchIsNotAPress:
    """Browsers prefetch and prerender pages nobody has opened — the tab
    strips ask them to — and an event recorded then would count readers
    who never arrived."""

    def test_a_prerender_request_records_nothing(self, client, tester, gang_type):
        client.force_login(tester)
        found_one(client, gang_type)
        Event.objects.all().delete()

        found_one(
            client,
            gang_type,
            name="Never Opened",
            headers={"Sec-Purpose": "prefetch;prerender"},
        )
        assert not Event.objects.exists()


class TestFoundingAGangIsRecorded:
    """The first thing anyone asks of a new edition is how many people
    started."""

    def test_the_event_says_gang_and_says_n26(self, client, tester, gang_type):
        client.force_login(tester)
        found_one(client, gang_type)

        event = Event.objects.get(noun=N26Noun.GANG)
        assert event.verb == "create"
        assert event.edition == "n26"
        assert event.owner == tester

    def test_it_is_never_filed_under_the_other_editions_word(
        self, client, tester, gang_type
    ):
        """A gang recorded as a "list" would be counted into n23's graphs,
        where nothing would look wrong."""
        client.force_login(tester)
        found_one(client, gang_type)

        assert not Event.objects.filter(noun="list").exists()
        assert not Event.objects.filter(edition="n23").exists()

    def test_the_row_it_points_at_is_the_gang(self, client, tester, gang_type):
        client.force_login(tester)
        found_one(client, gang_type)

        gang = Gang.objects.get()
        assert Event.objects.get(noun=N26Noun.GANG).object == gang

    def test_the_type_and_the_budget_travel_with_it(self, client, tester, gang_type):
        client.force_login(tester)
        found_one(client, gang_type)

        context = Event.objects.get(noun=N26Noun.GANG).context
        assert context["gang_type"] == "Goliath"
        assert context["starting_credits"] == 1000


class TestDeletingAGangIsRecorded:
    def test_the_press_is_recorded_as_a_deletion(self, client, tester, gang_type):
        client.force_login(tester)
        found_one(client, gang_type)
        gang = Gang.objects.get()

        client.post(reverse("n26-delete-gang", args=[gang.pk]))

        assert Event.objects.filter(
            noun=N26Noun.GANG, verb="delete", edition="n26"
        ).exists()


class TestTrackingNeverBreaksWhatItObserves:
    """A gang is founded or it is not; whether anyone was watching must not
    come into it."""

    def test_a_dead_log_stream_does_not_stop_the_founding(
        self, client, tester, gang_type
    ):
        client.force_login(tester)
        with patch(
            "gyrinx.analytics.models.track", side_effect=RuntimeError("stream down")
        ):
            found_one(client, gang_type)

        assert Gang.objects.filter(name="Rust in Peace").exists()

    def test_an_event_that_cannot_be_written_does_not_stop_the_founding(
        self, client, tester, gang_type
    ):
        client.force_login(tester)
        with patch.object(
            Event.objects, "create", side_effect=RuntimeError("table gone")
        ):
            found_one(client, gang_type)

        assert Gang.objects.filter(name="Rust in Peace").exists()
        assert not Event.objects.exists()


class TestOnePressIsOneEvent:
    """A page that wrote an event per row would turn a big roster into a
    pile of writes."""

    def test_printing_a_gang_records_one_row_carrying_the_count(
        self, client, tester, gang_type
    ):
        client.force_login(tester)
        found_one(client, gang_type)
        gang = Gang.objects.get()

        client.get(reverse("n26-print", args=[gang.pk]))

        printed = Event.objects.filter(noun=N26Noun.PRINT_RUN)
        assert printed.count() == 1
        assert "cards" in printed.get().context
