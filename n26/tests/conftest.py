"""Register the fixtures defined in n26.tests.fixtures for this test tree. Keep fixture
definitions there so each N26 test tree can import them without colliding with
same-named platform fixtures.
"""

from n26.tests.fixtures import *  # noqa: F401,F403
