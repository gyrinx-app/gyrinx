import pytest
from django.test import Client, override_settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from gyrinx.core.models.events import Event, EventNoun, EventVerb


@pytest.mark.django_db
def test_normal_request_passes_through():
    """Test that normal requests without SQL injection patterns work fine."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Normal request should pass through
    response = client.get("/lists/", {"page": "1", "type": "gang"})
    assert response.status_code == 200

    # No security events should be created
    assert Event.objects.filter(noun=EventNoun.SECURITY_THREAT).count() == 0


@pytest.mark.django_db
def test_sql_injection_updatexml_blocked():
    """Test that UPDATEXML SQL injection attempts are blocked."""
    client = Client()

    # Clear cache first
    cache.clear()

    # SQL injection attempt with UPDATEXML
    response = client.get(
        "/lists/",
        {
            "page": "1&page=2&type=UPDATEXML(null,CHAR(58,73,56,111,78,58,100,54,101,56,104),null)"
        },
    )
    assert response.status_code == 403
    assert b"Invalid request" in response.content

    # Event should be logged
    event = Event.objects.filter(
        noun=EventNoun.SECURITY_THREAT, verb=EventVerb.BLOCK
    ).first()
    assert event is not None
    assert event.context["security_type"] == "sql_injection"
    assert "UPDATEXML" in event.context["query_string"]


@pytest.mark.django_db
def test_sql_injection_union_select_blocked():
    """Test that UNION SELECT SQL injection attempts are blocked."""
    client = Client()

    # Clear cache first
    cache.clear()

    # SQL injection attempt with UNION SELECT
    response = client.get("/lists/", {"id": "1 UNION SELECT * FROM users"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_sql_injection_error_function_blocked():
    """Test that ERROR() function SQL injection attempts are blocked."""
    client = Client()

    # Clear cache first
    cache.clear()

    # SQL injection attempt with ERROR function
    response = client.get(
        "/lists/",
        {"page": "ERROR(CODE_POINTS_TO_STRING([73,56,111,78,45,116,54,109,53,100]))"},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_ip_rate_limiting():
    """Test that IPs are blocked for repeated SQL injection attempts."""
    client = Client()

    # Clear cache first
    cache.clear()

    # First SQL injection attempt
    response = client.get("/lists/", {"q": "UPDATEXML(1,2,3)"})
    assert response.status_code == 403
    assert b"Invalid request" in response.content

    # Second attempt from same IP should be immediately blocked
    response = client.get("/lists/", {"q": "normal query"})
    assert response.status_code == 403
    assert b"Blocked" in response.content


@pytest.mark.django_db
def test_authenticated_user_event_logging():
    """Test that events are logged with authenticated user info."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Clear cache first
    cache.clear()

    # SQL injection attempt by authenticated user
    response = client.get("/lists/", {"search": "CHAR(97,98,99)"})
    assert response.status_code == 403

    # Event should include user info
    event = Event.objects.filter(
        noun=EventNoun.SECURITY_THREAT, verb=EventVerb.BLOCK
    ).first()
    assert event is not None
    assert event.owner == user


@pytest.mark.django_db
def test_anonymous_user_event_logging():
    """Test that events are logged for anonymous users."""
    client = Client()

    # Clear cache first
    cache.clear()

    # SQL injection attempt by anonymous user
    response = client.get("/lists/", {"filter": "OR 1=1"})
    assert response.status_code == 403

    # Event should be created without owner
    event = Event.objects.filter(
        noun=EventNoun.SECURITY_THREAT, verb=EventVerb.BLOCK
    ).first()
    assert event is not None
    assert event.owner is None
    assert event.context["security_type"] == "sql_injection"


@pytest.mark.django_db
def test_case_insensitive_pattern_matching():
    """Test that SQL injection patterns are matched case-insensitively."""
    client = Client()

    # Clear cache first
    cache.clear()

    # Test various case combinations
    test_cases = [
        "updatexml(1,2,3)",
        "UPDATEXML(1,2,3)",
        "UpdateXml(1,2,3)",
        "union select",
        "UNION SELECT",
        "UnIoN sElEcT",
    ]

    for case in test_cases:
        cache.clear()  # Clear cache for each test
        response = client.get("/lists/", {"q": case})
        assert response.status_code == 403, f"Failed to block: {case}"


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_middleware_preserves_request_attributes():
    """Test that the middleware doesn't interfere with normal request processing."""
    client = Client()
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.force_login(user)

    # Make a request with various attributes
    response = client.post(
        "/lists/",
        {"name": "Test List", "type": "gang"},
        HTTP_USER_AGENT="Test Browser",
        HTTP_X_FORWARDED_FOR="192.168.1.1",
    )

    # Should not be blocked (no SQL injection pattern)
    assert response.status_code in [200, 302, 404]  # Normal status codes
