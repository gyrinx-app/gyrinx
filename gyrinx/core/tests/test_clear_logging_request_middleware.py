import pytest
from google.cloud.logging_v2.handlers.middleware.request import (
    _get_django_request,
    _thread_locals,
)


@pytest.mark.django_db
def test_logging_request_thread_local_cleared_after_response(client):
    """The google.cloud.logging RequestMiddleware stores each request in a
    thread-local and never clears it; ClearLoggingRequestMiddleware must wipe
    it after the response so reused server threads don't pin dead requests."""
    response = client.get("/")
    assert response.status_code == 200
    assert _get_django_request() is None


@pytest.mark.django_db
def test_logging_request_thread_local_cleared_after_error_response(client):
    """The clear must run even when the view errors (404 here)."""
    _thread_locals.request = None
    response = client.get("/definitely-not-a-real-page/")
    assert response.status_code == 404
    assert _get_django_request() is None
