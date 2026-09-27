"""Helpers shared by the tests: small example tables and a text extractor."""

import html
import re

import numpy as np

from ipyrowtable import (
    ChoiceColumn,
    NodeColumn,
    NumberColumn,
    OutputColumn,
    RowTable,
    TextColumn,
    Unit,
    UnitSystem,
)


def text(item) -> str:
    """Visible text of an HTML widget (or an HTML string): tags and entities removed,
    whitespace collapsed the way a browser renders it."""
    value = getattr(item, "value", item)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", value)).split())


# ------------------------------------------------------------------ a plane wall, with units

CONDUCTIVITY = {"steel": 50.0, "brick": 0.7, "foam": 0.035}  # W/m·K

METRIC = UnitSystem("metric", {
    "length": Unit("mm", 1000.0),
    "temperature": Unit("°C"),
    "flux": Unit("W/m²"),
    "resistance": Unit("m²·K/W"),
})
US = UnitSystem("US", {
    "length": Unit("in", 1 / 0.0254),
    "temperature": Unit("°F", 1.8, 32.0),
    "flux": Unit("Btu/hr·ft²", 0.3169983),
    "resistance": Unit("hr·ft²·°F/Btu", 5.678263),
})


def wall_compute(inputs):
    L = inputs.column("thickness").astype(float)
    if np.any(L <= 0):
        raise ValueError("Thickness must be > 0")
    k = np.array([CONDUCTIVITY[m] for m in inputs.column("material")])
    R = L / k
    T_first, T_last = inputs.edges["T"]
    q = (T_first - T_last) / R.sum()
    return {"R": R, "T": T_first - q * np.concatenate(([0.0], np.cumsum(R))), "q": q}


def make_wall(**options):
    config = dict(
        columns=[
            ChoiceColumn("material", "Material", options=CONDUCTIVITY),
            NumberColumn("thickness", "Thickness ({unit})", quantity="length",
                         default={"metric": 10.0, "US": 0.5}, min=0.0),
            OutputColumn("R", "R ({unit})", quantity="resistance"),
            NodeColumn("T", "T ({unit})", quantity="temperature",
                       first_default=100.0, last_default=20.0, fmt="{:.2f}"),
        ],
        compute=wall_compute,
        rows=[{"material": "steel", "thickness": 10.0}, {"material": "foam", "thickness": 50.0}],
        unit_systems=[METRIC, US],
        leading_label="— top —",
        item_name="layer",
        output_quantities={"q": "flux"},
    )
    config.update(options)
    return RowTable(**config)


# ------------------------------------------------------------------ a cable run, no units

OHM_PER_M = {"14 AWG": 0.00829, "12 AWG": 0.00521, "10 AWG": 0.00328}


def cable_compute(inputs):
    R = np.array([OHM_PER_M[g] for g in inputs.column("gauge")]) * inputs.column("length")
    drop = inputs.params["current"] * R
    V_source = inputs.edges["V"][0]
    return {"drop": drop, "V": V_source - np.concatenate(([0.0], np.cumsum(drop)))}


def make_cable(**options):
    config = dict(
        columns=[
            TextColumn("name", "Run"),
            ChoiceColumn("gauge", "Wire", options=OHM_PER_M),
            NumberColumn("length", "Length (m)", default=10.0, min=0.0),
            OutputColumn("drop", "Drop (V)"),
            NodeColumn("V", "Voltage (V)", inputs="first", first_default=120.0),
        ],
        compute=cable_compute,
        parameters=[NumberColumn("current", "Current (A)", default=15.0)],
        rows=[{"name": "a", "gauge": "12 AWG", "length": 20.0},
              {"name": "b", "gauge": "14 AWG", "length": 8.0}],
        leading_label="— source —",
        item_name="segment",
    )
    config.update(options)
    return RowTable(**config)
