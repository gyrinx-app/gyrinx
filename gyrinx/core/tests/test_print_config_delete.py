"""Print configuration delete confirmation page."""

import pytest
from django.urls import reverse

from gyrinx.core.models import PrintConfig


@pytest.mark.django_db
def test_delete_confirmation_back_link_resolves(client, user, make_list):
    """The back link resolves the print-config index URL rather than
    emitting the literal URL name (issue #2001)."""
    lst = make_list("Test Gang")
    config = PrintConfig.objects.create(list=lst, owner=user, name="My Config")
    client.force_login(user)

    response = client.get(reverse("core:print-config-delete", args=[lst.id, config.id]))
    assert response.status_code == 200
    content = response.content.decode()

    index_url = reverse("core:print-config-index", args=[lst.id])
    assert f'href="{index_url}"' in content
    assert 'href="core:print-config-index"' not in content
