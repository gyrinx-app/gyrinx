"""The edition dimension on the event log.

Two editions write to one table. These pin the three things that keeps
honest: a noun belongs to one edition only, every row gets an edition without
anyone passing one, and a noun nobody claimed lands somewhere visible rather
than in the wrong product's graph.
"""

from importlib import import_module
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured

from gyrinx.analytics.models import Event, EventVerb, log_event
from gyrinx.analytics.nouns import (
    Edition,
    PlatformNoun,
    edition_for_noun,
    noun_choices,
    register_nouns,
    registered_nouns,
)
from n23.core.events import EventNoun
from n26.analytics import N26Noun


def test_each_edition_claims_its_own_nouns():
    nouns = registered_nouns()
    assert nouns["list"][0] == Edition.N23
    assert nouns["gang"][0] == Edition.N26
    assert nouns["user"][0] == Edition.PLATFORM


def test_no_noun_means_something_in_two_editions():
    """The claim the derivation rests on: were "list" also n26's word, a
    stored row could not say which product it came from."""
    n23 = {value for value in EventNoun.values}
    n26 = {value for value in N26Noun.values}
    platform = {value for value in PlatformNoun.values}

    assert not n23 & n26
    assert not n23 & platform
    assert not n26 & platform


def test_claiming_another_editions_noun_is_refused():
    with pytest.raises(ImproperlyConfigured) as refusal:
        register_nouns(Edition.N26, [("list", "List")])

    assert "already registered" in str(refusal.value)


def test_an_unclaimed_noun_is_unknown_rather_than_guessed():
    assert edition_for_noun("no_such_noun") == Edition.UNKNOWN
    assert edition_for_noun(None) == Edition.UNKNOWN


def test_the_noun_dropdown_is_grouped_by_edition():
    grouped = dict(noun_choices())

    assert ("list", "List") in grouped["N23"]
    assert ("gang", "Gang") in grouped["N26"]
    assert ("user", "User") in grouped["Platform"]


@pytest.mark.django_db
def test_an_event_takes_its_edition_from_its_noun():
    user = User.objects.create_user(username="tracked")

    n23 = log_event(user=user, noun=EventNoun.LIST, verb=EventVerb.CREATE)
    n26 = log_event(user=user, noun=N26Noun.GANG, verb=EventVerb.CREATE)
    platform = log_event(user=user, noun=PlatformNoun.USER, verb=EventVerb.LOGIN)

    assert n23.edition == Edition.N23
    assert n26.edition == Edition.N26
    assert platform.edition == Edition.PLATFORM


@pytest.mark.django_db
def test_a_row_written_straight_to_the_model_is_classified_too():
    """Nothing has to go through log_event for the column to be filled in."""
    user = User.objects.create_user(username="direct")

    event = Event.objects.create(owner=user, noun=N26Noun.MODEL, verb=EventVerb.CREATE)

    assert event.edition == Edition.N26


@pytest.mark.django_db
def test_an_unclaimed_noun_still_records_the_event():
    user = User.objects.create_user(username="stranger")

    event = log_event(user=user, noun="mystery", verb=EventVerb.CREATE)

    assert event is not None
    assert event.edition == Edition.UNKNOWN


@pytest.mark.django_db
def test_the_stream_is_told_the_edition_as_well():
    """Both sinks or neither: a row in the table that the log stream files
    under no product is only half tracked."""
    user = User.objects.create_user(username="streamed")

    with patch("gyrinx.analytics.models.track") as track:
        log_event(user=user, noun=N26Noun.GANG, verb=EventVerb.CREATE)

    assert track.call_args.kwargs["edition"] == Edition.N26


@pytest.mark.django_db
def test_a_broken_stream_does_not_lose_the_row():
    user = User.objects.create_user(username="unlucky")

    with patch("gyrinx.analytics.models.track", side_effect=RuntimeError("down")):
        event = log_event(user=user, noun=EventNoun.LIST, verb=EventVerb.CREATE)

    assert Event.objects.filter(pk=event.pk).exists()


class TestBackfillingWhatWasAlreadyThere:
    """The migration's answer for rows written before the column existed."""

    migration = import_module("gyrinx.analytics.migrations.0002_event_edition")

    def test_account_and_banner_events_belong_to_neither_edition(self):
        assert self.migration.edition_for_existing_noun("user") == "platform"
        assert self.migration.edition_for_existing_noun("banner") == "platform"

    def test_everything_else_written_by_then_was_n23(self):
        for noun in ("list", "list_fighter", "campaign", "equipment_assignment"):
            assert self.migration.edition_for_existing_noun(noun) == "n23"

    def test_every_noun_the_old_vocabulary_had_is_answered(self):
        """The migration has to be total: a noun it does not recognise would
        keep the default and read as unknown forever."""
        old = set(EventNoun.values) | set(PlatformNoun.values)
        assert {self.migration.edition_for_existing_noun(n) for n in old} == {
            "platform",
            "n23",
        }
