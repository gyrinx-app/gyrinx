"""Verify unsaved authoring previews using scratch content and gangs. Cover Brawler skill
placements, a companion requirement, invalid payloads and the staff JSON endpoint.
Compare every model's row count before and after to detect writes escaping the preview
rollback; see n26/design/authoring-build-plan.md.
"""

import json

import pytest
from django.apps import apps

from n26.core.preview import PreviewError, preview

pytestmark = pytest.mark.django_db

BRAWLER_GRID = {
    "Outcast Leader": {
        "Combat": "Primary",
        "Savant": "Primary",
        "Brawn": "Secondary",
        "Cunning": "Secondary",
    },
    "Outcast Champion": {
        "Brawn": "Primary",
        "Combat": "Primary",
        "Savant": "Secondary",
    },
    "Outcast Hive Scum": {
        "Combat": "Primary",
        "Brawn": "Secondary",
        "Cunning": "Secondary",
    },
}


def placement_payload(rank, category, tier, bearer_only=False):
    """Composer payload for one rank/category placement."""
    payload = {
        "attach_to": "@Brawler",
        "scope_kind": "targets_model" if bearer_only else "targets_every_model",
        "effect_kind": "ef_places",
        "conditions-TOTAL_FORMS": "1",
        "conditions-INITIAL_FORMS": "0",
        "conditions-0-kind": "has_subtypes",
        "conditions-0-subtypes": [f"@{rank}"],
        "what-category": f"@{category}",
        "what-section": f"@{tier}",
    }
    return payload


def brawler_state():
    """Complete preview state for the Brawler placement grid."""
    return {
        "create": [
            *({"kind": "subtype", "name": rank} for rank in BRAWLER_GRID),
            *(
                {"kind": "category", "name": name}
                for name in ("Combat", "Savant", "Brawn", "Cunning")
            ),
            {
                "kind": "collection",
                "name": "Skills & Powers",
                "sections": ["Primary", "Secondary"],
            },
            {"kind": "affiliation", "name": "Brawler"},
        ],
        "modifiers": [
            placement_payload(
                rank, category, tier, bearer_only=(rank == "Outcast Champion")
            )
            for rank, cells in BRAWLER_GRID.items()
            for category, tier in cells.items()
        ],
        "gang": {"carries": ["@Brawler"]},
        "fighters": [{"name": "Scratch Leader", "subtypes": ["@Outcast Leader"]}],
    }


def row_counts():
    """Count rows for every registered Django model."""
    return {
        model._meta.label: model.objects.count()
        for app in apps.get_app_configs()
        for model in app.get_models()
    }


@pytest.fixture
def unchanged_database(db):
    before = row_counts()
    yield
    assert row_counts() == before, "the preview leaked rows into the database"


class TestTheBrawlerGrid:
    def test_the_scratch_leader_shows_the_leaders_row(
        self, default_pack, unchanged_database
    ):
        result = preview(brawler_state())

        (leader,) = result.cards
        assert leader["name"] == "Scratch Leader"
        assert "Combat under Primary" in leader["placements"]
        assert "Savant under Primary" in leader["placements"]
        assert sorted(leader["placements"]) == [
            "Brawn under Secondary",
            "Combat under Primary",
            "Cunning under Secondary",
            "Savant under Primary",
        ]

    def test_the_plan_carries_all_ten_placement_steps(
        self, default_pack, unchanged_database
    ):
        result = preview(brawler_state())

        (leader,) = result.cards
        placement_steps = [step for step in leader["plan"] if "puts" in step]
        assert len(placement_steps) == 10
        reached = [step for step in placement_steps if "reached" in step]
        assert len(reached) == 4

    def test_the_gang_block_is_a_scratch_gang(self, default_pack, unchanged_database):
        result = preview(brawler_state())
        assert result.gang["name"] == "Scratch gang"
        assert result.gang["rating"] == 0  # Scratch models are hired without payment.


class TestLeadTheMasses:
    def state(self):
        return {
            "create": [
                {"kind": "subtype", "name": "Outcast Champion"},
                {"kind": "subtype", "name": "Outcast Hive Scum"},
                {"kind": "rule", "name": "Lead the Masses"},
            ],
            "modifiers": [
                {
                    "attach_to": "@Lead the Masses",
                    "scope_kind": "targets_gang",
                    "effect_kind": "ef_requires_companions",
                    "what-for_each": "@Outcast Champion",
                    "what-at_least": "3",
                    "what-of": "@Outcast Hive Scum",
                }
            ],
            "gang": {"carries": ["@Lead the Masses"]},
            "fighters": [
                {"name": "Scratch Champion", "subtypes": ["@Outcast Champion"]},
                {"name": "Scratch Scum", "subtypes": ["@Outcast Hive Scum"]},
            ],
        }

    def test_the_note_fires_on_a_short_roster(self, default_pack, unchanged_database):
        result = preview(self.state())
        (note,) = result.notes
        assert "need 3 Outcast Hive Scum" in note
        assert "the gang has 1" in note


class TestRefusals:
    def test_a_bad_payload_is_words_and_no_rows(self, default_pack, unchanged_database):
        state = {
            "create": [{"kind": "rule", "name": "Lead the Masses"}],
            "modifiers": [
                {
                    "attach_to": "@Lead the Masses",
                    "scope_kind": "targets_gang",
                    "effect_kind": "ef_requires_companions",
                    # Omit every required effect field.
                }
            ],
        }
        with pytest.raises(PreviewError) as refusal:
            preview(state)
        assert any(
            "what for_each" in error for error in refusal.value.errors["__all__"]
        )

    def test_an_unknown_reference_says_so(self, default_pack, unchanged_database):
        state = {"gang": {"carries": ["@Nothing"]}}
        with pytest.raises(PreviewError, match="Nothing"):
            preview(state)


class TestTheEndpoint:
    """The staff-only preview endpoint accepts form state as JSON and returns scratch card
    data or validation errors.
    """

    @pytest.fixture(autouse=True)
    def staff_client(self, client):
        from django.contrib.auth.models import User

        client.force_login(User.objects.create_user("previewer", is_staff=True))
        # Warm the session before unchanged_database captures row counts. This autouse
        # fixture runs before requested fixtures.
        client.get("/n26/")

    def test_post_gives_back_card_state(self, client, default_pack, unchanged_database):
        response = client.post(
            "/n26/preview/",
            json.dumps(brawler_state()),
            content_type="application/json",
        )
        assert response.status_code == 200
        body = response.json()
        (leader,) = body["cards"]
        assert "Combat under Primary" in leader["placements"]
        assert body["gang"]["name"] == "Scratch gang"

    def test_a_refused_payload_is_a_400_in_words(
        self, client, default_pack, unchanged_database
    ):
        state = {"gang": {"carries": ["@Nothing"]}}
        response = client.post(
            "/n26/preview/", json.dumps(state), content_type="application/json"
        )
        assert response.status_code == 400
        assert "Nothing" in str(response.json()["errors"])

    def test_not_json_is_a_400(self, client, default_pack, unchanged_database):
        response = client.post(
            "/n26/preview/", "not json", content_type="application/json"
        )
        assert response.status_code == 400
