import pytest
from django.template.loader import render_to_string

from n26.designsystem import sampledata


@pytest.mark.django_db
class TestCardTooltipsAreReal:
    def test_the_rating_badge_carries_a_tooltip_not_a_title(self):
        html = render_to_string(
            "cotton/n26/model_card/index.html",
            {"card": sampledata.model_card(), "mode": "edit"},
        )
        assert 'title="Rating' not in html
        assert 'title="Learn' not in html
        assert 'title="From' not in html
        assert 'title="Granted' not in html
        assert html.count('role="tooltip"') >= 1
