import pytest


@pytest.mark.django_db
def test_robots_txt_served_as_plain_text(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")


@pytest.mark.django_db
def test_robots_txt_policy(client):
    """Amazonbot and Bytespider are excluded entirely; fighter detail pages,
    accounts, and admin are disallowed for every agent."""
    body = client.get("/robots.txt").content.decode()
    sections = body.split("\n\n")
    assert "User-agent: Amazonbot\nDisallow: /" in sections
    assert "User-agent: Bytespider\nDisallow: /" in sections
    general = [s for s in sections if s.startswith("User-agent: *")][0]
    assert "Disallow: /list/*/fighter/" in general
    assert "Disallow: /accounts/" in general
    assert "Disallow: /admin/" in general
