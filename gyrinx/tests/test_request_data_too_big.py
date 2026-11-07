"""Return HTTP 400 for RequestDataTooBig, including template-rendering fallback."""

from unittest.mock import patch

import pytest
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse
from django.template import TemplateDoesNotExist
from django.test import RequestFactory, override_settings

from gyrinx.middleware import RequestSizeExceptionMiddleware

pytestmark = pytest.mark.core


def test_request_size_exception_middleware_catches_exception():

    middleware = RequestSizeExceptionMiddleware(lambda r: HttpResponse("OK"))

    request = HttpRequest()
    request.method = "POST"

    exception = RequestDataTooBig("Request body exceeded settings.")

    with patch(
        "gyrinx.middleware.render", return_value=HttpResponse("Error", status=400)
    ):
        response = middleware.process_exception(request, exception)

    assert response is not None, "Middleware should return a response"
    assert response.status_code == 400, f"Expected 400 but got {response.status_code}"


def test_request_size_exception_middleware_fallback():

    middleware = RequestSizeExceptionMiddleware(lambda r: HttpResponse("OK"))

    request = HttpRequest()
    request.method = "POST"

    exception = RequestDataTooBig("Request body exceeded settings.")

    with patch(
        "gyrinx.middleware.render",
        side_effect=TemplateDoesNotExist("errors/error.html"),
    ):
        response = middleware.process_exception(request, exception)

    assert response is not None, "Middleware should return a fallback response"
    assert response.status_code == 400, f"Expected 400 but got {response.status_code}"
    assert response["Content-Type"] == "text/plain"


def test_request_size_exception_middleware_ignores_other_exceptions():

    middleware = RequestSizeExceptionMiddleware(lambda r: HttpResponse("OK"))

    request = HttpRequest()
    request.method = "POST"

    exception = ValueError("Some other error")

    response = middleware.process_exception(request, exception)

    assert response is None, "Middleware should not handle other exceptions"


def test_request_data_too_big_exception_behavior():

    from django.core.exceptions import SuspiciousOperation

    with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=100):
        try:
            raise RequestDataTooBig("Request body exceeded settings.")
        except RequestDataTooBig as e:
            assert isinstance(e, SuspiciousOperation), (
                "RequestDataTooBig should be a SuspiciousOperation"
            )


@pytest.mark.django_db
def test_full_middleware_chain_returns_400():

    factory = RequestFactory()
    request = factory.post("/upload", data={"field": "x" * 200})

    def get_response(r):
        raise RequestDataTooBig("Request body exceeded settings.")

    middleware = RequestSizeExceptionMiddleware(get_response)
    exception = RequestDataTooBig("Request body exceeded settings.")

    response = middleware.process_exception(request, exception)

    assert response is not None, "Middleware should return a response"
    assert response.status_code == 400
    assert b"Request Too Large" in response.content


@pytest.mark.django_db
def test_middleware_call_wraps_downstream_exceptions():

    factory = RequestFactory()
    request = factory.get("/")

    middleware = RequestSizeExceptionMiddleware(
        lambda r: HttpResponse("OK", status=200)
    )
    response = middleware(request)
    assert response.status_code == 200

    exception = RequestDataTooBig("Request body exceeded settings.")
    with patch(
        "gyrinx.middleware.render", return_value=HttpResponse("Error", status=400)
    ):
        response = middleware.process_exception(request, exception)
    assert response.status_code == 400
