"""
Base classes and utilities for content models.

This module provides the abstract Content base class that all content models
inherit from. The Content class inherits from gyrinx.models.Base which provides:
- UUID primary key
- created/modified timestamps
"""

from dataclasses import dataclass

from gyrinx.models import Base


class Content(Base):
    """
    An abstract base model that captures common fields for all content-related
    models. Subclasses should inherit from this to store standard metadata.
    """

    class Meta:
        abstract = True


@dataclass
class RulelineDisplay:
    """A dataclass for displaying rules in a consistent format."""

    value: str
    modded: bool = False


@dataclass
class StatlineDisplay:
    """A dataclass for displaying stats in a consistent format."""

    name: str
    field_name: str
    value: str
    classes: str = ""
    modded: bool = False
    highlight: bool = False
