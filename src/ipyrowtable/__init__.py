"""ipyrowtable: editable ipywidgets tables of elements in series.

Each row is an element (a layer, a pipe segment, a cable run, ...) with input columns the
user edits and output columns your compute function fills in. Rows can be added and
removed, values *between* rows (temperatures at interfaces, pressures at joints) get their
own column with editable boundary conditions, and an optional toggle switches unit systems.

    from ipyrowtable import RowTable, NumberColumn, OutputColumn

    table = RowTable(
        columns=[NumberColumn("x", "x", default=1.0), OutputColumn("x2", "x²")],
        compute=lambda inputs: {"x2": inputs.column("x") ** 2},
    )
    table

See the example notebooks, and ipyrowtable.examples.conduction for a complete application.
"""

from .columns import (
    ChoiceColumn,
    Column,
    InputColumn,
    NodeColumn,
    NumberColumn,
    OutputColumn,
    TextColumn,
)
from .figure import LiveFigure
from .formatting import fmt_sig
from .layout import side_by_side
from .table import RowTable, TableInputs, TableResults
from .units import Unit, UnitSystem

__version__ = "0.1.0"

__all__ = [
    "RowTable",
    "TableInputs",
    "TableResults",
    "Column",
    "InputColumn",
    "ChoiceColumn",
    "NumberColumn",
    "TextColumn",
    "OutputColumn",
    "NodeColumn",
    "Unit",
    "UnitSystem",
    "LiveFigure",
    "side_by_side",
    "fmt_sig",
    "__version__",
]
