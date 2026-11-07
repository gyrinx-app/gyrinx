import random
from itertools import combinations

import pytest

from n26.core.matchmaking import (
    Entrant,
    Matchup,
    Mode,
    NoMatchup,
    make_matchups,
    matchup_sizes,
)


def gang(name, rating=1000, *, last=(), last_size=None, earlier=()):
    """A gang whose latest battle was against `last`, then each of `earlier`."""
    recent = ()
    if last:
        size = len(last) + 1 if last_size is None else last_size
        recent = ((frozenset(last), size),)
    recent += tuple((frozenset(them), len(them) + 1) for them in earlier)
    return Entrant(id=name, name=name, rating=rating, recent=recent)


def seeded(seed):
    # Seeded only so a failure can be replayed; matchmaking uses SystemRandom.
    return random.Random(seed)  # nosec B311


def names(matchups):
    return [{gang.name for gang in matchup.gangs} for matchup in matchups]


class TestSizes:
    def test_the_gangs_decide_how_many_matchups(self):
        assert matchup_sizes(8, 2, allow_uneven=False) == [2, 2, 2, 2]
        assert matchup_sizes(8, 4, allow_uneven=False) == [4, 4]
        assert matchup_sizes(9, 3, allow_uneven=False) == [3, 3, 3]

    def test_one_spare_gang_makes_the_first_matchup_larger(self):
        assert matchup_sizes(5, 2, allow_uneven=True) == [3, 2]
        assert matchup_sizes(9, 4, allow_uneven=True) == [5, 4]

    def test_a_spare_gang_needs_uneven_sides(self):
        with pytest.raises(
            NoMatchup,
            match="Select 4 or 6 gangs, or tick Allow uneven sides to add a spare gang.",
        ):
            matchup_sizes(5, 2, allow_uneven=False)

    @pytest.mark.parametrize("count", [0, 1])
    @pytest.mark.parametrize("ways", [2, 3, 8])
    @pytest.mark.parametrize("allow_uneven", [False, True])
    def test_a_battle_needs_at_least_two_gangs(self, count, ways, allow_uneven):
        with pytest.raises(NoMatchup, match="Select at least 2 gangs."):
            matchup_sizes(count, ways, allow_uneven=allow_uneven)

    def test_too_few_gangs_for_one_battle_are_refused(self):
        with pytest.raises(
            NoMatchup, match="Select at least 4 gangs for battles of 4."
        ):
            matchup_sizes(3, 4, allow_uneven=True)

    @pytest.mark.parametrize(
        "allow_uneven, message",
        [
            (False, "Select 6 or 9 gangs for battles of 3."),
            (True, "Select 6, 7 or 9 gangs for battles of 3."),
        ],
    )
    def test_more_than_one_spare_gang_is_refused(self, allow_uneven, message):
        with pytest.raises(NoMatchup, match=message):
            matchup_sizes(8, 3, allow_uneven=allow_uneven)

    @pytest.mark.parametrize("ways", [2, 3, 8])
    @pytest.mark.parametrize("count", range(2, 33))
    def test_every_matchup_has_at_least_two_gangs(self, ways, count):
        try:
            sizes = matchup_sizes(count, ways, allow_uneven=True)
        except NoMatchup:
            return
        assert sum(sizes) == count
        assert min(sizes) >= 2


class TestExampleOne:
    """Adam last played Ben, and Chris last played David."""

    gangs = [
        gang("Adam", last={"Ben"}),
        gang("Ben", last={"Adam"}),
        gang("Chris", last={"David"}),
        gang("David", last={"Chris"}),
    ]

    @pytest.mark.parametrize("seed", range(20))
    def test_no_pair_repeats_a_latest_battle(self, seed):
        found = make_matchups(self.gangs, ways=2, rng=seeded(seed))
        assert len(found) == 2
        for pair in names(found):
            assert pair not in ({"Adam", "Ben"}, {"Chris", "David"})

    def test_allowing_rematches_allows_any_pairing(self):
        seen = set()
        for seed in range(40):
            found = make_matchups(self.gangs, ways=2, lookback=0, rng=seeded(seed))
            seen.update(frozenset(pair) for pair in names(found))
        assert frozenset({"Adam", "Ben"}) in seen

    def test_only_the_latest_battle_counts(self):
        # Adam fought Ben before, but has fought Chris since.
        gangs = [gang("Adam", last={"Chris"}), gang("Ben"), gang("Chris")]
        found = make_matchups(gangs[:2], ways=2)
        assert names(found) == [{"Adam", "Ben"}]


class TestExampleTwo:
    """Five gangs in pairs, with uneven sides allowed."""

    gangs = [
        gang("Adam", 1050),
        gang("Ben", 1020),
        gang("Chris", 1000),
        gang("David", 2000),
        gang("Emily", 900),
    ]

    @pytest.mark.parametrize("seed", range(20))
    def test_the_spare_gang_joins_the_highest_rated_gang(self, seed):
        found = make_matchups(self.gangs, ways=2, allow_uneven=True, rng=seeded(seed))
        sizes = sorted(len(matchup.gangs) for matchup in found)
        assert sizes == [2, 3]
        larger = max(found, key=lambda matchup: len(matchup.gangs))
        assert "David" in {gang.name for gang in larger.gangs}

    def test_without_uneven_sides_the_spare_gang_is_refused(self):
        with pytest.raises(NoMatchup):
            make_matchups(self.gangs, ways=2)


class TestImpossibleMatchups:
    def test_it_says_when_every_combination_is_a_rematch(self):
        gangs = [gang("Adam", last={"Ben"}), gang("Ben", last={"Adam"})]
        with pytest.raises(NoMatchup, match="Tick Allow rematches"):
            make_matchups(gangs, ways=2)

    def test_a_rematch_counts_from_either_side(self):
        # Ben's latest battle was against Adam; Adam has not played since.
        gangs = [gang("Adam"), gang("Ben", last={"Adam"})]
        with pytest.raises(NoMatchup):
            make_matchups(gangs, ways=2)


class TestLargerBattles:
    """A pair may meet again when more gangs join them."""

    def test_a_pair_may_meet_again_in_a_three_way_battle(self):
        gangs = [gang("Adam", last={"Ben"}), gang("Ben", last={"Adam"}), gang("Chris")]
        found = make_matchups(gangs, ways=3)
        assert names(found) == [{"Adam", "Ben", "Chris"}]

    def test_the_spare_gang_can_make_a_pair_a_larger_battle(self):
        gangs = [
            gang("Adam", 2000, last={"Ben"}),
            gang("Ben", last={"Adam"}),
            gang("Chris"),
        ]
        found = make_matchups(gangs, ways=2, allow_uneven=True)
        assert names(found) == [{"Adam", "Ben", "Chris"}]

    def test_gangs_from_a_three_way_battle_may_not_meet_as_a_pair(self):
        gangs = [
            gang("Adam", last={"Ben", "Chris"}),
            gang("Ben", last={"Adam", "Chris"}),
        ]
        with pytest.raises(NoMatchup, match="Tick Allow rematches"):
            make_matchups(gangs, ways=2)

    def test_a_battle_the_same_size_is_still_a_rematch(self):
        gangs = [
            gang("A", last={"B", "C"}),
            gang("B", last={"A", "C"}),
            gang("C", last={"A", "B"}),
        ]
        with pytest.raises(NoMatchup):
            make_matchups(gangs, ways=3)

    def test_either_gangs_latest_battle_sets_the_size(self):
        # Adam has since played a four-way battle; Ben's latest is still the pair.
        gangs = [
            gang("Adam", last={"X", "Y", "Z"}),
            gang("Ben", last={"Adam"}),
        ]
        with pytest.raises(NoMatchup):
            make_matchups(gangs, ways=2)


class TestRematchWindow:
    """Ticked, Allow rematches keeps apart gangs that met in recent battles."""

    # Adam's battles, newest first: Ben, then Chris, then Dan.
    adam = gang("Adam", last={"Ben"}, earlier=[{"Chris"}, {"Dan"}])

    def can_meet(self, opponent, lookback):
        try:
            make_matchups([self.adam, gang(opponent)], ways=2, lookback=lookback)
        except NoMatchup:
            return False
        return True

    def test_by_default_only_the_latest_battle_counts(self):
        assert not self.can_meet("Ben", 1)
        assert self.can_meet("Chris", 1)

    def test_zero_allows_any_rematch(self):
        assert self.can_meet("Ben", 0)

    def test_a_larger_window_counts_more_past_battles(self):
        assert not self.can_meet("Ben", 2)
        assert not self.can_meet("Chris", 2)
        assert self.can_meet("Dan", 2)
        assert not self.can_meet("Dan", 3)

    def test_the_window_names_itself_when_nothing_works(self):
        with pytest.raises(NoMatchup, match="a rematch within 3 past matches"):
            make_matchups([self.adam, gang("Dan")], ways=2, lookback=3)

    def test_a_larger_battle_is_still_never_a_rematch(self):
        found = make_matchups(
            [self.adam, gang("Ben"), gang("Chris")], ways=3, lookback=3
        )
        assert names(found) == [{"Adam", "Ben", "Chris"}]


class TestMatchMore:
    @pytest.mark.parametrize("seed", range(10))
    def test_every_gang_plays_once(self, seed):
        gangs = [gang(f"G{index}") for index in range(8)]
        found = make_matchups(gangs, ways=4, rng=seeded(seed))
        played = [gang.name for matchup in found for gang in matchup.gangs]
        assert sorted(played) == sorted(gang.name for gang in gangs)

    def test_gangs_from_a_battle_as_large_do_not_meet_again(self):
        gangs = [
            gang("A", last={"B"}, last_size=3),
            gang("B", last={"A"}, last_size=3),
            gang("C"),
            gang("D"),
            gang("E"),
            gang("F"),
        ]
        for seed in range(20):
            for matchup in make_matchups(gangs, ways=3, rng=seeded(seed)):
                ids = {gang.id for gang in matchup.gangs}
                assert not {"A", "B"} <= ids


class TestAvoid:
    def test_rerolling_proposes_a_different_combination(self):
        gangs = [gang(name) for name in "ABCD"]
        first = make_matchups(gangs, ways=2, rng=seeded(1))
        avoid = {frozenset(g.id for g in matchup.gangs) for matchup in first}
        again = make_matchups(gangs, ways=2, avoid=avoid, rng=seeded(1))
        assert not avoid & {frozenset(g.id for g in m.gangs) for m in again}

    def test_one_result_cannot_be_rerolled(self):
        gangs = [gang("A"), gang("B")]
        with pytest.raises(NoMatchup, match="Select more results to rematch"):
            make_matchups(gangs, ways=2, avoid={frozenset({"A", "B"})})


class TestTitles:
    def test_pairs_name_the_gangs(self):
        pair = Matchup((gang("Adam"), gang("Ben")))
        assert pair.title(1, Mode.PAIRS) == "Matchup 1: Adam vs Ben"

    def test_larger_battles_count_the_gangs(self):
        four = Matchup(tuple(gang(name) for name in "ABCD"))
        assert four.title(1, Mode.MORE) == "Matchup 1: 4-way match"

    def test_long_titles_fit_the_scenario_field(self):
        pair = Matchup((gang("A" * 150), gang("B" * 150)))
        assert len(pair.title(1, Mode.PAIRS)) == 200


def test_every_pairing_is_reachable():
    gangs = [gang(name) for name in "ABCD"]
    seen = set()
    for seed in range(60):
        for matchup in make_matchups(gangs, ways=2, rng=seeded(seed)):
            seen.add(frozenset(g.id for g in matchup.gangs))
    assert seen == {frozenset(pair) for pair in combinations("ABCD", 2)}
