"""Declare N26 feature slugs and expose the shared platform flag checks. Registration
identifies edition features; access settings remain in the platform FeatureFlag records.
"""

from gyrinx.site.flags import enabled, register_flags, requires_flag, switched_on

__all__ = [
    "BUILT_IN_PROPAGATION",
    "CYCLE_TRACKING",
    "STAGED_CONTENT",
    "enabled",
    "requires_flag",
    "switched_on",
]

#: Built-in edits still record propagation work while disabled; execution waits until the
#: flag is enabled.
BUILT_IN_PROPAGATION = "built-in-propagation"

#: Allow non-staff accounts to preview staged content through a selected group. Staff
#: access is checked separately.
STAGED_CONTENT = "staged-content"

#: Gate campaign scheduling and cycle attribution independently of campaign access.
CYCLE_TRACKING = "campaign-cycles"

register_flags(BUILT_IN_PROPAGATION, STAGED_CONTENT, CYCLE_TRACKING)
