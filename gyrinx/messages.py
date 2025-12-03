# Re-export all messages from django.contrib.messages
from django.contrib import messages
from django.contrib.messages import *  # noqa: F403
from django.core.exceptions import ValidationError


def validation(request, e: ValidationError) -> str:
    error_message = ". ".join(e.messages)
    messages.error(request, error_message)
    return error_message
