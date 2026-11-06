"""Request SQL metadata survives the supported OpenTelemetry middleware."""

import pytest
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import ResolverMatch
from django.utils.module_loading import import_string


@pytest.mark.django_db
@pytest.mark.parametrize("query_count", [1, 5])
def test_sql_comments_preserve_request_metadata_without_extra_queries(
    query_count, settings
):
    settings.MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        *settings.MIDDLEWARE,
    ]

    def view(request):
        for _ in range(query_count):
            with connection.cursor() as cursor:
                cursor.execute("SELECT %s", [17])
                assert cursor.fetchone() == (17,)
        return HttpResponse("ok")

    request = RequestFactory().get("/security-probe/")
    request.resolver_match = ResolverMatch(
        view,
        (),
        {},
        url_name="security_probe",
        app_names=["core"],
        route="security-probe/",
    )
    middleware_path = "opentelemetry.instrumentation.django.middleware.sqlcommenter_middleware.SqlCommenter"
    assert middleware_path in settings.MIDDLEWARE
    middleware = import_string(middleware_path)(view)

    with CaptureQueriesContext(connection) as queries:
        response = middleware(request)

    assert response.status_code == 200
    assert len(queries) == query_count
    for query in queries.captured_queries:
        sql = query["sql"]
        assert "controller='security_probe'" in sql
        assert "app_name='core'" in sql
        assert "framework='django" in sql
        assert "route='security-probe" in sql
        assert "traceparent=" not in sql
        assert "db_driver=" not in sql

    with CaptureQueriesContext(connection) as outside:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 18")
            assert cursor.fetchone() == (18,)
    assert len(outside) == 1
    assert "controller=" not in outside[0]["sql"]
