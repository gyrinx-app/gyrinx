import json
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from gyrinx.core.models import Event, EventNoun, EventVerb, List, log_event


@pytest.mark.django_db
def test_event_model_creation():
    """Test basic Event model creation."""
    user = User.objects.create_user(username="testuser")
    event = Event.objects.create(
        owner=user,
        noun=EventNoun.LIST,
        verb=EventVerb.CREATE,
        ip_address="192.168.1.1",
        context={"list_name": "Test List"},
    )

    assert event.owner == user
    assert event.noun == EventNoun.LIST
    assert event.verb == EventVerb.CREATE
    assert event.ip_address == "192.168.1.1"
    assert event.context == {"list_name": "Test List"}
    assert str(event).startswith("testuser create list at")


@pytest.mark.django_db
def test_event_with_object_reference():
    """Test Event creation with object reference."""
    user = User.objects.create_user(username="testuser")
    list_obj = List.objects.create(owner=user, name="Test List", house="TEST_HOUSE")

    event = Event.objects.create(
        owner=user,
        noun=EventNoun.LIST,
        verb=EventVerb.UPDATE,
        object_id=list_obj.pk,
        object_type=ContentType.objects.get_for_model(List),
    )

    assert event.object_id == list_obj.pk
    assert event.object_type == ContentType.objects.get_for_model(List)
    assert event.object == list_obj


@pytest.mark.django_db
def test_log_event_utility():
    """Test the log_event utility function."""
    user = User.objects.create_user(username="testuser")
    list_obj = List.objects.create(owner=user, name="Test List", house="TEST_HOUSE")

    event = log_event(
        user=user,
        noun=EventNoun.LIST,
        verb=EventVerb.CREATE,
        object=list_obj,
        ip_address="192.168.1.1",
        list_name="Test List",
        fighter_count=5,
    )

    assert event.owner == user
    assert event.noun == EventNoun.LIST
    assert event.verb == EventVerb.CREATE
    assert event.object_id == list_obj.pk
    assert event.object_type == ContentType.objects.get_for_model(List)
    assert event.ip_address == "192.168.1.1"
    assert event.context == {"list_name": "Test List", "fighter_count": 5}


@pytest.mark.django_db
def test_log_event_without_object():
    """Test log_event without an object reference."""
    user = User.objects.create_user(username="testuser")

    event = log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        ip_address="192.168.1.1",
        action="password_change",
    )

    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.UPDATE
    assert event.object_id is None
    assert event.object_type is None
    assert event.context == {"action": "password_change"}


@pytest.mark.django_db
@patch("gyrinx.core.models.events.logger")
def test_event_logging_to_stream(mock_logger):
    """Test that events are logged to the log stream."""
    user = User.objects.create_user(username="testuser")

    event = Event.objects.create(
        owner=user,
        noun=EventNoun.LIST,
        verb=EventVerb.CREATE,
        ip_address="192.168.1.1",
        context={"list_name": "Test List"},
    )

    # Check that logger.info was called
    mock_logger.info.assert_called_once()

    # Verify the log message
    call_args = mock_logger.info.call_args
    assert call_args[0][0] == "USER_EVENT: create list"

    # Verify the extra data contains JSON
    event_data = json.loads(call_args[1]["extra"]["event_data"])
    assert event_data["id"] == str(event.id)
    assert event_data["username"] == "testuser"
    assert event_data["noun"] == EventNoun.LIST
    assert event_data["verb"] == EventVerb.CREATE
    assert event_data["ip_address"] == "192.168.1.1"
    assert event_data["context"] == {"list_name": "Test List"}


@pytest.mark.django_db
def test_event_noun_choices():
    """Test EventNoun enum values."""
    assert EventNoun.LIST == "list"
    assert EventNoun.LIST_FIGHTER == "list_fighter"
    assert EventNoun.CAMPAIGN == "campaign"
    assert EventNoun.BATTLE == "battle"
    assert EventNoun.EQUIPMENT_ASSIGNMENT == "equipment_assignment"
    assert EventNoun.SKILL_ASSIGNMENT == "skill_assignment"
    assert EventNoun.USER == "user"
    assert EventNoun.UPLOAD == "upload"
    assert EventNoun.FIGHTER_ADVANCEMENT == "fighter_advancement"
    assert EventNoun.CAMPAIGN_ACTION == "campaign_action"
    assert EventNoun.CAMPAIGN_RESOURCE == "campaign_resource"
    assert EventNoun.CAMPAIGN_ASSET == "campaign_asset"


@pytest.mark.django_db
def test_event_verb_choices():
    """Test EventVerb enum values."""
    assert EventVerb.CREATE == "create"
    assert EventVerb.UPDATE == "update"
    assert EventVerb.DELETE == "delete"
    assert EventVerb.ARCHIVE == "archive"
    assert EventVerb.RESTORE == "restore"
    assert EventVerb.VIEW == "view"
    assert EventVerb.CLONE == "clone"
    assert EventVerb.JOIN == "join"
    assert EventVerb.LEAVE == "leave"
    assert EventVerb.ASSIGN == "assign"
    assert EventVerb.UNASSIGN == "unassign"
    assert EventVerb.ACTIVATE == "activate"
    assert EventVerb.DEACTIVATE == "deactivate"
    assert EventVerb.SUBMIT == "submit"
    assert EventVerb.APPROVE == "approve"
    assert EventVerb.REJECT == "reject"
    assert EventVerb.IMPORT == "import"
    assert EventVerb.EXPORT == "export"
