"""Expose N26 maintenance task routes through the application registry.

The registry reads task_routes from this module. Task implementations live
behind the platform integration in n26.maintenance.
"""

from n26.maintenance import task_routes

__all__ = ["task_routes"]
