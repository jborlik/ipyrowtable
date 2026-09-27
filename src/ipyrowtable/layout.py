"""Layout helpers."""

from __future__ import annotations

import ipywidgets as widgets

__all__ = ["side_by_side"]


def side_by_side(*items, gap: str = "24px") -> widgets.HBox:
    """Lay widgets out in a row that wraps onto new lines when the notebook is narrow."""
    for item in items[1:]:
        item.layout.margin = f"0 0 0 {gap}"
    return widgets.HBox(
        list(items), layout=widgets.Layout(flex_flow="row wrap", align_items="flex-start")
    )
