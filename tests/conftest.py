"""Shared fixtures.

The widgets are ordinary ipywidgets objects, so they can be built and driven from plain
Python without a browser or a kernel: setting ``widget.value`` is exactly what happens when
a user types in a box, and ``button.click()`` runs the same handlers as a mouse click.
"""

import pytest

from tests.helpers import make_cable, make_wall


@pytest.fixture
def wall():
    """A two-layer plane wall with metric / US units and editable boundary temperatures."""
    return make_wall()


@pytest.fixture
def cable():
    """A two-segment cable run: no units, a current parameter, source voltage input only."""
    return make_cable()
