"""
Test for RequestDataTooBig exception handling.

This test verifies that when a request body exceeds DATA_UPLOAD_MAX_MEMORY_SIZE,
the server returns a 400 Bad Request (not a 500 Internal Server Error).

Issue: https://github.com/gyrinx-app/gyrinx/issues/1097
"""

from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse

from gyrinx.core.middleware import RequestSizeExceptionMiddleware


def test_request_size_exception_middleware_catches_exception():
    """
    Test that RequestSizeExceptionMiddleware catches RequestDataTooBig
    and returns a 400 response.
    """
    # Create middleware instance
    middleware = RequestSizeExceptionMiddleware(lambda r: HttpResponse("OK"))

    # Create a mock request
    request = HttpRequest()
    request.method = "POST"

    # Create the exception
    exception = RequestDataTooBig("Request body exceeded settings.")

    # The middleware should catch it and return 400
    response = middleware.process_exception(request, exception)

    assert response is not None, "Middleware should return a response"
    assert response.status_code == 400, f"Expected 400 but got {response.status_code}"


def test_request_size_exception_middleware_ignores_other_exceptions():
    """
    Test that RequestSizeExceptionMiddleware ignores other exceptions.
    """
    # Create middleware instance
    middleware = RequestSizeExceptionMiddleware(lambda r: HttpResponse("OK"))

    # Create a mock request
    request = HttpRequest()
    request.method = "POST"

    # Create a different exception
    exception = ValueError("Some other error")

    # The middleware should return None (not handle it)
    response = middleware.process_exception(request, exception)

    assert response is None, "Middleware should not handle other exceptions"


def test_request_data_too_big_exception_behavior():
    """
    Test that demonstrates the bug: RequestDataTooBig is a SuspiciousOperation
    exception, but Django's default handling may not properly convert it to 400.

    This test verifies the exception is raised correctly and can be caught.
    """

    from django.test import override_settings

    # Create a mock request-like object to trigger the exception
    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=100):
        # The exception should be raisable and catchable
        try:
            raise RequestDataTooBig("Request body exceeded settings.")
        except RequestDataTooBig as e:
            # Verify the exception is a SuspiciousOperation
            from django.core.exceptions import SuspiciousOperation

            assert isinstance(e, SuspiciousOperation), (
                "RequestDataTooBig should be a SuspiciousOperation"
            )


import pytest


@pytest.mark.django_db
def test_django_handler_with_request_data_too_big(client):
    """
    Test that verifies RequestDataTooBig is properly handled as a 400 error.

    This test simulates the full middleware stack by using Django's test client
    to ensure that RequestSizeExceptionMiddleware catches the exception and
    returns a 400 response.
    """
    from django.core.exceptions import RequestDataTooBig
    from django.urls import path
    from django.test.utils import override_settings

    # Create a view that raises RequestDataTooBig when accessed
    def view_that_raises_request_too_big(request):
        # This simulates what happens when request body exceeds limits
        raise RequestDataTooBig("Request body exceeded settings.")

    # Create a temporary URL pattern for testing
    urlpatterns = [
        path("test-request-too-big/", view_that_raises_request_too_big),
    ]

    # Override ROOT_URLCONF to include our test URL
    with override_settings(
        ROOT_URLCONF=__name__,
        # Ensure our middleware is in the stack
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
            "gyrinx.core.middleware.RequestSizeExceptionMiddleware",  # Our middleware
        ],
    ):
        # Make the urlpatterns available in this module for the override
        import sys

        sys.modules[__name__].urlpatterns = urlpatterns

        # Use the test client to make a request that will go through the full middleware stack
        response = client.post("/test-request-too-big/", data={"field": "x" * 200})

        # Verify that the middleware caught the exception and returned 400
        assert response.status_code == 400, (
            f"Expected status code 400 but got {response.status_code}. "
            f"The RequestSizeExceptionMiddleware should catch RequestDataTooBig and return 400."
        )


@pytest.mark.django_db
def test_actual_large_request_returns_400(client):
    """
    Test that an actual large request that exceeds DATA_UPLOAD_MAX_MEMORY_SIZE
    returns a 400 status code through the full middleware stack.

    This simulates the real-world scenario where Django raises RequestDataTooBig
    when parsing the request body.
    """
    from django.test import override_settings
    from django.urls import path
    from django.http import HttpResponse

    # Create a simple view that tries to access request data
    def simple_view(request):
        # Accessing request.POST will trigger request body parsing
        _ = request.POST
        return HttpResponse("OK")

    # Create a temporary URL pattern for testing
    urlpatterns = [
        path("test-large-upload/", simple_view),
    ]

    # Set a very small upload limit to trigger the exception
    with override_settings(
        ROOT_URLCONF=__name__,
        DATA_UPLOAD_MAX_MEMORY_SIZE=100,  # 100 bytes limit
        # Ensure our middleware is in the stack
        MIDDLEWARE=[
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
            "gyrinx.core.middleware.RequestSizeExceptionMiddleware",  # Our middleware
        ],
        # Disable CSRF for this test
        CSRF_USE_SESSIONS=False,
        CSRF_COOKIE_HTTPONLY=False,
    ):
        # Make the urlpatterns available in this module for the override
        import sys

        sys.modules[__name__].urlpatterns = urlpatterns

        # Create a large payload that exceeds the limit
        large_data = {"field": "x" * 1000}  # Much larger than 100 bytes

        # Disable CSRF checking for this specific request
        from django.views.decorators.csrf import csrf_exempt

        sys.modules[__name__].simple_view = csrf_exempt(simple_view)
        urlpatterns[0] = path("test-large-upload/", csrf_exempt(simple_view))

        # Use the test client to POST the large data
        response = client.post("/test-large-upload/", data=large_data)

        # Verify that we get a 400 response, not 500
        assert response.status_code == 400, (
            f"Expected status code 400 for oversized request but got {response.status_code}. "
            f"The middleware should intercept RequestDataTooBig and return 400."
        )
