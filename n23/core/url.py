from django.conf import settings
from django.http import HttpRequest


def fullurl(request: HttpRequest, path):
    base_url = getattr(settings, "BASE_URL", None)
    if base_url:
        return base_url.rstrip("/") + "/" + path.lstrip("/")
    return request.build_absolute_uri(path)
