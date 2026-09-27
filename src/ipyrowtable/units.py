"""Unit systems: how each physical quantity is displayed.

Values are always stored (and passed to your compute function) in *base* units, whatever
units your compute function works in. A UnitSystem only changes what is shown:

    display = base * scale + offset
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["Unit", "UnitSystem"]


@dataclass(frozen=True)
class Unit:
    """How one quantity is displayed: ``display = base * scale + offset``.

    Examples
    --------
    >>> Unit("mm", 1000.0)               # base unit metres
    >>> Unit("°F", 1.8, 32.0)            # base unit °C
    """

    label: str
    scale: float = 1.0
    offset: float = 0.0


@dataclass(frozen=True)
class UnitSystem:
    """A named set of display units, one per quantity name.

    Quantity names are free-form strings you choose ("length", "temperature", "flow", ...).
    Quantities the system doesn't list are shown in base units with no label.

    Examples
    --------
    >>> SI = UnitSystem("SI", {"length": Unit("mm", 1000.0), "temperature": Unit("°C")})
    >>> SI.to_display("length", 0.01)
    10.0
    """

    name: str
    units: dict = field(default_factory=dict)

    def label(self, quantity: str | None) -> str:
        """The unit label for a quantity, or "" if the system doesn't list it."""
        unit = self.units.get(quantity)
        return unit.label if unit else ""

    def to_display(self, quantity, value):
        """Convert a base value (scalar or array) to display units."""
        unit = self.units.get(quantity)
        if unit is None:
            return value
        return _scalar(np.asarray(value, dtype=float) * unit.scale + unit.offset)

    def to_base(self, quantity, value):
        """Convert a display value (scalar or array) to base units."""
        unit = self.units.get(quantity)
        if unit is None:
            return value
        return _scalar((np.asarray(value, dtype=float) - unit.offset) / unit.scale)


def _scalar(a):
    return float(a) if np.ndim(a) == 0 else a
