"""The roster tally: one list, two readings, and the totals that check them.

``summarise_roster`` is a pure reduction over the members ``roster``
returns, so these tests hand it plain namespaces — the contract is
attribute-shaped, and a database would only slow the point down.
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
        """Drill-kyn the Specialist and Drill-kyn the Ganger are different
        answers to "what does this gang field", so they are not merged."""
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
        """The tally keeps the roster's own order: a pet's row lands after
        its first keeper's, the way the gang list prints them."""
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
        """A rule that moves a model (ChangesCategory) is already folded
        into the list's order. The tally uses that same rank, so it does
        not count a model as a Ganger while listing it among Champions."""
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
        """A profile filed nowhere is still fielded: it groups under an
        empty rank rather than vanishing from the tally."""
        summary = summarise_roster([member("Stray", 10, "Techmite", None)])
        assert summary.groups[0].category == ""
        assert summary.count == 1
