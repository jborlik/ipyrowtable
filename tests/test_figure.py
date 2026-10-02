import sys

import numpy as np
import pytest

pytest.importorskip("matplotlib")

from ipyrowtable import LiveFigure, side_by_side  # noqa: E402
from tests.helpers import text  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def draw_profile(fig, results):
    ax = fig.add_subplot()
    ax.plot(results.display("T"), np.arange(len(results["T"])))


def test_renders_png_on_creation(wall):
    fig = LiveFigure(wall, draw=draw_profile, size=(4, 3), dpi=100)
    assert bytes(fig.value).startswith(PNG_MAGIC)
    assert fig.layout.visibility == "visible"
    assert fig.layout.width.endswith("px")


def test_redraws_on_every_change(wall):
    calls = []
    LiveFigure(wall, draw=lambda f, r: calls.append(r["q"]), dpi=50)
    wall.cell(0, "thickness").value = 20.0
    wall.units = "US"
    assert len(calls) == 3


def test_width_follows_the_rendered_image(wall):
    fig = LiveFigure(wall, draw=draw_profile, size=(4, 3), dpi=100, tight=False)
    assert fig.layout.width == "400px"


def test_hidden_while_inputs_are_invalid(wall):
    fig = LiveFigure(wall, draw=draw_profile, dpi=50)
    before = fig.value
    wall.cell(0, "thickness").value = 0.0
    assert fig.layout.visibility == "hidden"
    assert fig.value == before  # keeps its space and last image
    wall.cell(0, "thickness").value = 5.0
    assert fig.layout.visibility == "visible"


def test_subclass_draw(wall):
    class Profile(LiveFigure):
        def draw(self, fig, results):
            self.drawn = results["q"]

    fig = Profile(wall, dpi=50)
    assert fig.drawn == wall.results["q"]


def test_draw_must_be_provided(wall):
    with pytest.raises(NotImplementedError):
        LiveFigure(wall)


def test_draw_errors_after_creation_are_shown_under_the_table(wall):
    state = {"fail": False}

    def draw(fig, results):
        if state["fail"]:
            raise RuntimeError("bad axes")

    LiveFigure(wall, draw=draw, dpi=50)
    state["fail"] = True
    wall.cell(0, "thickness").value = 20.0
    assert "RuntimeError: bad axes" in text(wall.message)


def test_missing_matplotlib_gives_install_hint(wall, monkeypatch):
    monkeypatch.setitem(sys.modules, "matplotlib.figure", None)
    with pytest.raises(ImportError, match=r"ipyrowtable\[plot\]"):
        LiveFigure(wall, draw=draw_profile)


def test_side_by_side(wall):
    fig = LiveFigure(wall, draw=draw_profile, dpi=50)
    box = side_by_side(wall, fig, gap="10px")
    assert list(box.children) == [wall, fig]
    assert box.layout.grid_gap == "0 10px"  # between items on a line, not after wrapping
    assert fig.layout.margin == "0"
    assert box.layout.flex_flow == "row wrap"
