"""The shared fixtures, registered for tests/.

The fixture definitions live in tests/fixtures.py — an importable
module, not a root conftest — so each test-bearing tree registers them
with a one-line conftest like this one. The repo root deliberately has
no conftest: when this repo lands inside a larger one, a root conftest
would collide with the host's (both define make_statline), and the
loser would lose silently.
"""

from n26.tests.fixtures import *  # noqa: F401,F403
