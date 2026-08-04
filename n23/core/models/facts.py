"""Immutable facts dataclasses for cost-bearing models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AssignmentFacts:
    """Immutable facts about an equipment assignment."""

    rating: int


@dataclass(frozen=True)
class FighterFacts:
    """Immutable facts about a fighter."""

    rating: int


@dataclass(frozen=True)
class ListFacts:
    """Immutable facts about a list."""

    rating: int
    stash: int
    credits: int

    @property
    def wealth(self) -> int:
        """Total wealth = rating + stash + credits."""
        return self.rating + self.stash + self.credits
