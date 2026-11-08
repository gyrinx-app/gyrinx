"""Roster summaries group by effective profile and rank while preserving model order
and totals.

Simple namespaces supply the attributes used by this pure reduction.
"""

from types import SimpleNamespace

from n26.core.render import summarise_roster


def member(name, rating, profile, category, pk=None):
    return SimpleNamespace(
        pk=pk,
        name=name,
        rating=rating,
        membership=SimpleNamespace(
            profile=SimpleNamespace(
                name=profile,
                category=SimpleNamespace(name=category) if category else None,
            )
        ),
    )


class TestTheProfilesReading:
    def test_one_row_per_profile_and_rank_counted(self):
        summary = summarise_roster(
            [
                member("Doug", 325, "Charter Master", "Leader"),
                member("Whiskers", 40, "Gyrinx Cat", "Pet"),
                member("Kin", 45, "Drill-kyn", "Specialist"),
                member("Vex", 45, "Drill-kyn", "Specialist"),
            ]
        )
        rows = [(g.profile, g.category, g.count) for g in summary.groups]
        assert rows == [
            ("Charter Master", "Leader", 1),
            ("Gyrinx Cat", "Pet", 1),
            ("Drill-kyn", "Specialist", 2),
        ]

    def test_one_profile_at_two_ranks_is_two_rows(self):
        """Keep different ranks separate even when their profile names match."""
        summary = summarise_roster(
            [
                member("Kin", 45, "Drill-kyn", "Specialist"),
                member("Vex", 45, "Drill-kyn", "Ganger"),
            ]
        )
        assert [(g.category, g.count) for g in summary.groups] == [
            ("Specialist", 1),
            ("Ganger", 1),
        ]

    def test_a_group_sits_where_its_first_member_does(self):
        """Position each group at its first occurrence in roster order."""
        summary = summarise_roster(
            [
                member("Doug", 325, "Charter Master", "Leader"),
                member("Whiskers", 40, "Gyrinx Cat", "Pet"),
                member("Freshly Hired", 130, "Charter Master", "Leader"),
                member("Mittens", 40, "Gyrinx Cat", "Pet"),
            ]
        )
        assert [g.profile for g in summary.groups] == [
            "Charter Master",
            "Gyrinx Cat",
        ]
        assert [g.count for g in summary.groups] == [2, 2]

    def test_a_refiled_model_groups_under_the_rank_the_roster_sorted_it_at(self):
        """Use the effective category so the tally agrees with rule-driven roster
        placement.
        """
        champion = SimpleNamespace(name="Champion")
        summary = summarise_roster(
            [
                member("Doug", 325, "Charter Master", "Leader", pk=1),
                member("Promoted", 55, "Ganger", "Ganger", pk=2),
            ],
            recategorised={2: champion},
        )
        assert [(g.profile, g.category, g.count) for g in summary.groups] == [
            ("Charter Master", "Leader", 1),
            ("Ganger", "Champion", 1),
        ]


class TestTheRatingsReading:
    def test_every_model_with_its_rating_and_the_total(self):
        summary = summarise_roster(
            [
                member("Doug", 325, "Charter Master", "Leader"),
                member("Kin", 45, "Drill-kyn", "Specialist"),
            ]
        )
        assert [(line.name, line.rating) for line in summary.models] == [
            ("Doug", 325),
            ("Kin", 45),
        ]
        assert summary.rating == 370
        assert summary.count == 2

    def test_an_unranked_profile_still_counts(self):
        """Include profiles with no category under an empty rank label."""
        summary = summarise_roster([member("Stray", 10, "Techmite", None)])
        assert summary.groups[0].category == ""
        assert summary.count == 1
