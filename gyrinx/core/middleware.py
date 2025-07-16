import logging
import re
from django.core.cache import cache
from django.http import HttpResponseForbidden

from gyrinx.core.models.events import EventNoun, EventVerb, get_client_ip, log_event


logger = logging.getLogger(__name__)


class BlockSQLInjectionMiddleware:
    """
    Middleware to detect and block SQL injection attempts.

    This middleware inspects incoming requests for common SQL injection patterns
    and blocks suspicious requests while logging them as security events.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Compile regex patterns for common SQL injection attempts
        self.sql_patterns = re.compile(
            r"(UPDATEXML|EXTRACTVALUE|CONCAT|CHAR\(|UNION.*SELECT|OR\s+\d+=\d+|WAITFOR|BENCHMARK|ERROR\(|CODE_POINTS_TO_STRING)",
            re.IGNORECASE,
        )

    def __call__(self, request):
        # Check query string for SQL injection patterns
        query_string = request.META.get("QUERY_STRING", "")

        if self.sql_patterns.search(query_string):
            # Get client IP for rate limiting
            ip = get_client_ip(request)
            cache_key = f"blocked_sql_injection_{ip}"

            # Check if this IP is already blocked
            if cache.get(cache_key):
                logger.warning(f"SQL injection attempt from already blocked IP: {ip}")
                return HttpResponseForbidden("Blocked")

            # Block IP for 1 hour (3600 seconds)
            cache.set(cache_key, True, 3600)

            # Log the security event with the full query string in context
            logger.warning(
                f"SQL injection attempt blocked from IP: {ip}, Query: {query_string[:200]}..."
            )

            # Create security event to track the blocked SQL injection attempt
            log_event(
                user=request.user if request.user.is_authenticated else None,
                noun=EventNoun.SECURITY_THREAT,
                verb=EventVerb.BLOCK,
                request=request,
                security_type="sql_injection",
                blocked_ip=ip,
                query_string=query_string[:1000],  # Truncate to avoid huge logs
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                path=request.path,
                method=request.method,
            )

            return HttpResponseForbidden("Invalid request")

        # Process the request normally if no SQL injection detected
        response = self.get_response(request)
        return response
