"""Column types for RowTable.

Input columns (edited by the user):   ChoiceColumn, NumberColumn, TextColumn
Output columns (filled by compute):   OutputColumn, NodeColumn

Input columns can also be used as table-wide *parameters* (shown above the table).
To make a new input type, subclass InputColumn and implement ``create_widget``; override
``to_display``, ``to_base`` and ``refresh`` if the widget shows something other than the
stored value.
"""

from __future__ import annotations

import math

import ipywidgets as widgets

from .formatting import formatter, right_aligned, tidy

__all__ = [
    "Column",
    "InputColumn",
    "NumberColumn",
    "ChoiceColumn",
    "TextColumn",
    "OutputColumn",
    "NodeColumn",
]


class _UnitLabels(dict):
    """format_map helper: {unit} is the column's own unit, {<quantity>} any quantity's unit."""

    def __init__(self, units, quantity):
        super().__init__()
        self.units, self.quantity = units, quantity

    def __missing__(self, key):
        return self.units.label(self.quantity if key == "unit" else key)


class Column:
    """Base class for all columns.

    key     identifies the column in rows, compute outputs and results
    header  string shown at the top; may use {unit} for this column's unit or {<quantity>}
            for any other quantity's unit, e.g. "Material (k in {conductivity})".
            Can also be a callable(units) -> str.
    width   CSS width of the grid column
    """

    width = "120px"
    quantity = None

    def __init__(self, key: str, header=None, width: str | None = None):
        self.key = key
        self.header = key if header is None else header
        if width is not None:
            self.width = width

    def header_text(self, units) -> str:
        if callable(self.header):
            return self.header(units)
        return self.header.format_map(_UnitLabels(units, self.quantity))

    def __repr__(self):
        return f"{type(self).__name__}({self.key!r})"


class InputColumn(Column):
    """Base for editable columns and parameters. Values are held in base units.

    default  value for new rows, in base units; or a dict {unit-system name: display value}
             for defaults that are round numbers in each system.
    """

    def __init__(self, key, header=None, default=None, width=None):
        super().__init__(key, header, width)
        self.default = default

    def default_value(self, units):
        """The default in base units, for the given unit system."""
        if isinstance(self.default, dict):
            return self.to_base(self.default[units.name], units)
        return self.default

    def to_display(self, value, units):
        """Convert a stored (base) value to what the widget shows."""
        return value

    def to_base(self, value, units):
        """Convert a widget value to the stored (base) value."""
        return value

    def create_widget(self, value, units):
        """Return a new widget showing `value` (base units). Must have a `value` trait."""
        raise NotImplementedError

    def refresh(self, widget, value, units):
        """Show `value` (base units) in `widget` after a unit-system change."""
        widget.value = self.to_display(value, units)

    def validate(self, value):
        """Check a saved value (base units) before it is restored; return it, possibly
        normalized, or raise ValueError. The default accepts anything."""
        return value


class NumberColumn(InputColumn):
    """A number per row.

    quantity  name of the quantity in your UnitSystems (e.g. "length"); None = unitless
    min, max  bounds in base units; if either is given the box clamps to them
    """

    def __init__(self, key, header=None, quantity=None, default=0.0, min=None, max=None,
                 width=None):
        super().__init__(key, header, default, width)
        self.quantity, self.min, self.max = quantity, min, max

    def to_display(self, value, units):
        return tidy(units.to_display(self.quantity, value))

    def to_base(self, value, units):
        return float(units.to_base(self.quantity, value))

    def _bounds(self, units):
        lo = -1e300 if self.min is None else units.to_display(self.quantity, self.min)
        hi = 1e300 if self.max is None else units.to_display(self.quantity, self.max)
        return lo, hi

    def create_widget(self, value, units):
        layout = widgets.Layout(width="100%")
        if self.min is None and self.max is None:
            return widgets.FloatText(value=self.to_display(value, units), layout=layout)
        lo, hi = self._bounds(units)
        return widgets.BoundedFloatText(
            value=self.to_display(value, units), min=lo, max=hi, step=None, layout=layout
        )

    def refresh(self, widget, value, units):
        if isinstance(widget, widgets.BoundedFloatText):
            lo, hi = self._bounds(units)
            with widget.hold_trait_notifications():
                widget.min, widget.max = lo, hi
        widget.value = self.to_display(value, units)

    def validate(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{self.key}: expected a number, got {value!r}")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{self.key}: {value} is not a finite number")
        # allow for round-off from converting through display units
        if self.min is not None and value < self.min - 1e-9 * max(1.0, abs(self.min)):
            raise ValueError(f"{self.key}: {value:g} is below the minimum {self.min:g}")
        if self.max is not None and value > self.max + 1e-9 * max(1.0, abs(self.max)):
            raise ValueError(f"{self.key}: {value:g} is above the maximum {self.max:g}")
        return value


class ChoiceColumn(InputColumn):
    """A dropdown; the row value is the chosen option's key.

    options  dict {key: data} or a list of keys. The data (e.g. a material property) is
             available to your compute function via the column's `options` dict.
    label    optional callable(key, data, units) -> str for the dropdown text, e.g. to show
             a property of each option in the current units
    default  initially selected key (default: the first)
    """

    width = "250px"

    def __init__(self, key, header=None, options=(), label=None, default=None, width=None):
        options = dict(options) if isinstance(options, dict) else {k: k for k in options}
        if not options:
            raise ValueError(f"ChoiceColumn {key!r} needs at least one option.")
        super().__init__(key, header, next(iter(options)) if default is None else default, width)
        self.options, self.label = options, label

    def _choices(self, units):
        if self.label is None:
            return list(self.options)
        return [(self.label(k, v, units), k) for k, v in self.options.items()]

    def create_widget(self, value, units):
        if value not in self.options:
            raise ValueError(f"{value!r} is not one of the {self.key!r} options.")
        return widgets.Dropdown(
            options=self._choices(units), value=value, layout=widgets.Layout(width="100%")
        )

    def refresh(self, widget, value, units):
        if self.label is not None:
            widget.options = self._choices(units)  # this resets the selection...
        widget.value = value  # ...so restore it

    def validate(self, value):
        if value not in self.options:
            raise ValueError(f"{self.key}: {value!r} is not one of the options")
        return value


class TextColumn(InputColumn):
    """Free text per row (e.g. a name or tag); updates when the box loses focus."""

    width = "160px"

    def __init__(self, key, header=None, default="", width=None):
        super().__init__(key, header, default, width)

    def create_widget(self, value, units):
        return widgets.Text(
            value=value, continuous_update=False, layout=widgets.Layout(width="100%")
        )

    def validate(self, value):
        if not isinstance(value, str):
            raise ValueError(f"{self.key}: expected text, got {value!r}")
        return value


class OutputColumn(Column):
    """One computed value per row, shown right-aligned.

    quantity  name of the quantity in your UnitSystems, for conversion and {unit} in headers
    fmt       None (4 significant figures), a format string like "{:.2f}", or a callable
    """

    width = "150px"

    def __init__(self, key, header=None, quantity=None, fmt=None, width=None):
        super().__init__(key, header, width)
        self.quantity, self.format = quantity, formatter(fmt)

    def render(self, value, units) -> str:
        return right_aligned(self.format(units.to_display(self.quantity, value)))


class NodeColumn(OutputColumn):
    """Computed values *between* rows: n + 1 values for n rows.

    The first value belongs to the top/inlet, shown in a leading row above the first element;
    each row then shows the value at its bottom/outlet face.

    inputs         which ends are editable boundary conditions: ("first", "last") (default),
                   "first", "last" or ()
    first_default  default for the first end, in base units, or {unit-system name: value}
    last_default   the same for the last end
    min, max       bounds for the editable ends, in base units
    """

    width = "120px"

    def __init__(self, key, header=None, quantity=None, inputs=("first", "last"),
                 first_default=0.0, last_default=0.0, min=None, max=None, fmt=None, width=None):
        super().__init__(key, header, quantity, fmt, width)
        inputs = (inputs,) if isinstance(inputs, str) else tuple(inputs)
        if set(inputs) - {"first", "last"}:
            raise ValueError("NodeColumn inputs must be drawn from 'first' and 'last'.")
        self.inputs = inputs
        self.ends = {
            "first": NumberColumn(key, quantity=quantity, default=first_default, min=min, max=max),
            "last": NumberColumn(key, quantity=quantity, default=last_default, min=min, max=max),
        }
