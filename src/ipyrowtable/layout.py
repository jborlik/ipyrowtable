"""Layout helpers."""

from __future__ import annotations

import ipywidgets as widgets

__all__ = ["side_by_side"]


def side_by_side(*items, gap: str = "24px") -> widgets.HBox:
    """Lay widgets out in a row that wraps onto new lines when the notebook is narrow."""
    # A gap, unlike a margin on each item, only goes between items on the same line, so an
    # item that wraps onto its own line doesn't stick out by the gap and make the row scroll.
    return widgets.HBox(list(items), layout=widgets.Layout(
        flex_flow="row wrap", align_items="flex-start", grid_gap=f"0 {gap}",
    ))
