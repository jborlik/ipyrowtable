"""LiveFigure: a matplotlib figure kept in sync with a RowTable."""

from __future__ import annotations

import io

import ipywidgets as widgets

__all__ = ["LiveFigure"]


class LiveFigure(widgets.Image):
    """A matplotlib figure redrawn from a table's results after every change.

    Pass ``draw=function(fig, results)``, or subclass and implement ``draw(self, fig, results)``.
    The figure is hidden (keeping its space) while the table's inputs are invalid. Errors
    raised while drawing are shown under the table.

    Parameters
    ----------
    table : RowTable
    draw : callable(matplotlib.figure.Figure, TableResults), optional
    size : (width, height) in inches; shown at 100 px per inch
    dpi : render resolution; 200 is crisp on high-DPI screens
    facecolor : figure background
    tight : grow or trim the canvas to fit everything drawn (e.g. labels outside the axes)

    Needs matplotlib: ``pip install ipyrowtable[plot]``.
    """

    def __init__(self, table, draw=None, size=(6.8, 4.4), dpi=200, facecolor="white",
                 tight=True):
        super().__init__(format="png")
        self.add_class("ipyrowtable-figure")
        # No margin: on a narrow screen the image shrinks to the full width, and a margin
        # would then stick out and make its container scroll.
        self.layout.margin = "0"
        self.table = table
        self.figsize, self.dpi, self.facecolor, self.tight = size, dpi, facecolor, tight
        if draw is not None:
            self.draw = draw
        table.on_update(self._render)

    def draw(self, fig, results):
        raise NotImplementedError("Pass draw=... or subclass LiveFigure and implement draw().")

    def _render(self, results):
        try:
            from matplotlib.figure import Figure  # no pyplot: nothing leaks into cell output
        except ImportError as exc:
            raise ImportError(
                "LiveFigure needs matplotlib: pip install ipyrowtable[plot]"
            ) from exc
        if results is None:
            self.layout.visibility = "hidden"
            return

        fig = Figure(figsize=self.figsize, facecolor=self.facecolor)
        self.draw(fig, results)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=self.dpi, facecolor=self.facecolor,
                    bbox_inches="tight" if self.tight else None, pad_inches=0.12)
        png = buf.getvalue()
        width_px = int.from_bytes(png[16:20], "big")  # from the PNG header
        self.layout.width = f"{round(width_px * 100 / self.dpi)}px"
        self.value = png
        self.layout.visibility = "visible"
