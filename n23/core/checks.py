"""Deploy-time system checks for the template layer.

Run automatically by `manage check`, which Cloud Build executes before deploy.
"""

from django.core.checks import Error, register


@register()
def cotton_is_wired_up(app_configs, **kwargs):
    """django-cotton fails OPEN, not closed.

    Cotton compiles ``<c-btn …>`` in the template LOADER. If the app ever leaves
    INSTALLED_APPS — a bad merge, a settings refactor, a deploy-config
    divergence — there is no loader, no builtin, and no exception: every
    component tag reaches the browser as literal text, unstyled, with HTTP 200.
    Only six test files assert on button/badge markup, so the suite would stay
    green against a completely unstyled application.

    This check turns that into a deploy-time failure.
    """
    from django.apps import apps
    from django.conf import settings

    errors = []
    # Asked of the app registry rather than the INSTALLED_APPS strings, because
    # development substitutes its own AppConfig subclass for the "django_cotton"
    # entry to drop the cached template loader (see gyrinx/cotton_dev.py). The app
    # is still installed under the same name; only the entry that names it differs.
    if not apps.is_installed("django_cotton"):
        errors.append(
            Error(
                "django_cotton is not in INSTALLED_APPS.",
                hint=(
                    "Every <c-…> component in gyrinx/templates/cotton/ would render "
                    "as literal text with HTTP 200 and no error."
                ),
                id="gyrinx.E001",
            )
        )
        return errors

    options = settings.TEMPLATES[0].get("OPTIONS", {})
    if not any("cotton" in b for b in options.get("builtins", [])):
        errors.append(
            Error(
                "The cotton templatetag library is not in TEMPLATES[0]['OPTIONS']['builtins'].",
                hint=(
                    "django_cotton's AppConfig.ready() injects it. If it is missing, "
                    "autoconfig did not run and components will not compile."
                ),
                id="gyrinx.E002",
            )
        )
    return errors
