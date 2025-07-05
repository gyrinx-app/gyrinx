import json
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from gyrinx.content.models import ContentHouse
from gyrinx.core.models import Event, EventNoun, EventVerb, List, log_event
from gyrinx.core.models.events import EventField, get_client_ip


@pytest.mark.django_db
def test_event_model_creation():
    """Test basic Event model creation."""
    user = User.objects.create_user(username="testuser")
    event = Event.objects.create(
        owner=user,
        noun=EventNoun.LIST,
        verb=EventVerb.CREATE,
        ip_address="192.168.1.1",
        session_id="test-session-123",
        context={"list_name": "Test List"},
    )

    assert event.owner == user
    assert event.noun == EventNoun.LIST
    assert event.verb == EventVerb.CREATE
    assert event.ip_address == "192.168.1.1"
    assert event.session_id == "test-session-123"
    assert event.context == {"list_name": "Test List"}
    assert str(event).startswith("testuser create list at")


@pytest.mark.django_db
def test_event_with_object_reference():
    """Test Event creation with object reference."""
    user = User.objects.create_user(username="testuser")
    house = ContentHouse.objects.create(name="Test House")
    list_obj = List.objects.create(owner=user, name="Test List", content_house=house)

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
    house = ContentHouse.objects.create(name="Test House")
    list_obj = List.objects.create(owner=user, name="Test List", content_house=house)

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
        field=EventField.PASSWORD,
    )

    assert event.owner == user
    assert event.noun == EventNoun.USER
    assert event.verb == EventVerb.UPDATE
    assert event.object_id is None
    assert event.object_type is None
    assert event.field == EventField.PASSWORD
    assert event.context == {}


@pytest.mark.django_db
def test_log_event_with_request_and_session():
    """Test log_event with request object containing session."""
    user = User.objects.create_user(username="testuser")

    # Mock request object with session
    mock_request = Mock()
    mock_request.session.session_key = "test-session-456"
    mock_request.META = {"REMOTE_ADDR": "192.168.1.2"}

    event = log_event(
        user=user,
        noun=EventNoun.LIST,
        verb=EventVerb.CREATE,
        request=mock_request,
    )

    assert event.owner == user
    assert event.noun == EventNoun.LIST
    assert event.verb == EventVerb.CREATE
    assert event.session_id == "test-session-456"
    assert event.ip_address == "192.168.1.2"


@pytest.mark.django_db
def test_log_event_with_request_no_session():
    """Test log_event with request but no session (e.g., API calls)."""
    user = User.objects.create_user(username="testuser")

    # Mock request object without session
    mock_request = Mock()
    mock_request.session = None
    mock_request.META = {"REMOTE_ADDR": "192.168.1.3"}

    event = log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.VIEW,
        request=mock_request,
    )

    assert event.owner == user
    assert event.session_id is None
    assert event.ip_address == "192.168.1.3"


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
        session_id="test-session-789",
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
    assert event_data["session_id"] == "test-session-789"
    assert event_data["field"] is None
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
    assert EventVerb.LOGIN == "login"
    assert EventVerb.LOGOUT == "logout"
    assert EventVerb.SIGNUP == "signup"


@pytest.mark.django_db
def test_event_subnoun_enum():
    """Test EventSubNoun enum values."""
    assert EventField.PASSWORD == "password"
    assert EventField.EMAIL == "email"


@pytest.mark.django_db
def test_create_list_view_logs_event(client, user, content_house):
    """Test that creating a list via the view logs an event."""
    from django.urls import reverse

    client.force_login(user)

    # Clear any existing events
    Event.objects.all().delete()

    # Create a list via the view
    response = client.post(
        reverse("core:lists-new"),
        {
            "name": "My Test Gang",
            "content_house": content_house.id,
            "public": True,
        },
    )

    # Should redirect after successful creation
    assert response.status_code == 302

    # Check that the list was created
    lst = List.objects.get(name="My Test Gang")
    assert lst.owner == user
    assert lst.content_house == content_house

    # Check that an event was logged
    assert Event.objects.count() == 1
    event = Event.objects.first()
    assert event.owner == user
    assert event.noun == EventNoun.LIST
    assert event.verb == EventVerb.CREATE
    assert event.object_id == lst.id
    assert event.object_type.model == "list"
    assert event.context["list_name"] == "My Test Gang"
    assert event.context["content_house"] == content_house.name
    assert event.context["public"] is True

    # Check that session ID was captured
    assert event.session_id is not None


@pytest.mark.django_db
@patch("gyrinx.core.models.events.Event.objects.create")
def test_log_event_error_handling(mock_create):
    """Test that log_event handles errors gracefully."""
    user = User.objects.create_user(username="testuser")

    # Make Event.objects.create raise an exception
    mock_create.side_effect = Exception("Database error")

    # This should not raise an exception
    result = log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.UPDATE,
        field=EventField.PASSWORD,
    )

    # Should return None when error occurs
    assert result is None

    # Verify create was attempted
    assert mock_create.called


@pytest.mark.django_db
@patch("gyrinx.core.models.events.logger")
def test_event_save_logging_error_handling(mock_logger):
    """Test that Event.save handles logging errors gracefully."""
    user = User.objects.create_user(username="testuser")

    # Make json.dumps fail by causing logger.info to raise
    mock_logger.info.side_effect = Exception("Logging error")

    # This should not raise an exception
    event = Event.objects.create(
        owner=user,
        noun=EventNoun.USER,
        verb=EventVerb.LOGIN,
    )

    # Event should still be created successfully
    assert event.id is not None
    assert Event.objects.count() == 1

    # Should have logged the exception
    mock_logger.exception.assert_called_once_with("Failed to log event to stream")


def test_get_client_ip_with_x_forwarded_for():
    """Test get_client_ip with X-Forwarded-For header."""
    mock_request = Mock()
    mock_request.META = {
        "HTTP_X_FORWARDED_FOR": "192.168.1.100, 10.0.0.1, 172.16.0.1",
        "REMOTE_ADDR": "10.0.0.1",
    }

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.100"


def test_get_client_ip_with_single_x_forwarded_for():
    """Test get_client_ip with single IP in X-Forwarded-For."""
    mock_request = Mock()
    mock_request.META = {
        "HTTP_X_FORWARDED_FOR": "192.168.1.100",
        "REMOTE_ADDR": "10.0.0.1",
    }

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.100"


def test_get_client_ip_with_x_real_ip():
    """Test get_client_ip with X-Real-IP header."""
    mock_request = Mock()
    mock_request.META = {"HTTP_X_REAL_IP": "192.168.1.200", "REMOTE_ADDR": "10.0.0.1"}

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.200"


def test_get_client_ip_fallback_to_remote_addr():
    """Test get_client_ip falls back to REMOTE_ADDR when no proxy headers."""
    mock_request = Mock()
    mock_request.META = {"REMOTE_ADDR": "192.168.1.1"}

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.1"


def test_get_client_ip_with_no_request():
    """Test get_client_ip with no request returns None."""
    ip = get_client_ip(None)
    assert ip is None


def test_get_client_ip_with_spaces_in_header():
    """Test get_client_ip handles spaces in X-Forwarded-For."""
    mock_request = Mock()
    mock_request.META = {
        "HTTP_X_FORWARDED_FOR": " 192.168.1.100 , 10.0.0.1 ",
        "REMOTE_ADDR": "10.0.0.1",
    }

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.100"


@pytest.mark.django_db
def test_log_event_with_x_forwarded_for():
    """Test log_event extracts IP from X-Forwarded-For header."""
    user = User.objects.create_user(username="testuser")

    mock_request = Mock()
    mock_request.session.session_key = "test-session"
    mock_request.META = {
        "HTTP_X_FORWARDED_FOR": "192.168.1.100, 10.0.0.1",
        "REMOTE_ADDR": "10.0.0.1",
    }

    event = log_event(
        user=user,
        noun=EventNoun.USER,
        verb=EventVerb.LOGIN,
        request=mock_request,
    )

    assert event.ip_address == "192.168.1.100"
