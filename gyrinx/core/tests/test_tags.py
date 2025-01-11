import pytest
from django.template.context import make_context as django_make_context

from gyrinx.core.templatetags.custom_tags import is_active


@pytest.fixture
def make_context(rf):
    def make_context_(path):
        return django_make_context(None, rf.get(path))

    return make_context_


def test_is_active(make_context):
    context = make_context("/")
    assert is_active(context, "core:index")
