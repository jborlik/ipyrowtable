"""RowTable: an editable table of elements with live computed outputs."""

from __future__ import annotations

import copy
import html
from dataclasses import dataclass, field
from pathlib import Path

import ipywidgets as widgets
import numpy as np

from .columns import Column, InputColumn, NodeColumn, OutputColumn
from .formatting import right_aligned
from .persistence import StateFile, StateFileError, default_state_file, persistence_enabled
from .units import UnitSystem

__all__ = ["RowTable", "TableInputs", "TableResults"]

_ENDS = ("first", "last")


@dataclass
class TableInputs:
    """What your compute function receives. All values are in base units.

    rows    list of dicts, one per row (top to bottom): {input column key: value}
    edges   {NodeColumn key: (first, last)}; an end that isn't an input is None
    params  {parameter key: value}
    """

    rows: list
    edges: dict
    params: dict

    def column(self, key) -> np.ndarray:
        """One input column as an array over rows, top to bottom."""
        return np.asarray([row[key] for row in self.rows])


@dataclass
class TableResults:
    """The inputs and compute outputs of one recompute, with unit-aware accessors.

    results[key] / results.base(key)   any output, parameter, NodeColumn boundary pair or
                                       input column, in base units
    results.display(key)               the same in the display units in use at the time
    results.records()                  one dict per row, mirroring the table
    """

    inputs: TableInputs
    outputs: dict
    units: UnitSystem
    quantities: dict
    columns: tuple = field(default=())

    def base(self, key):
        for source in (self.outputs, self.inputs.params, self.inputs.edges):
            if key in source:
                return source[key]
        if self.inputs.rows and key in self.inputs.rows[0]:
            return self.inputs.column(key)
        raise KeyError(key)

    def __getitem__(self, key):
        return self.base(key)

    def __contains__(self, key):
        try:
            self.base(key)
        except KeyError:
            return False
        return True

    def display(self, key):
        """The value of `key` converted to display units."""
        return self.units.to_display(self.quantities.get(key), self.base(key))

    def records(self, display: bool = True) -> list[dict]:
        """One dict per row with every column's value, as the table shows it.

        NodeColumns give the value at each row's bottom/outlet face. Handy for
        ``pandas.DataFrame(results.records())``.
        """
        get = self.display if display else self.base
        records = [{} for _ in self.inputs.rows]
        for col in self.columns:
            if isinstance(col, InputColumn):
                values = get(col.key)
            elif col.key in self.outputs:
                values = get(col.key)
                if isinstance(col, NodeColumn):
                    values = values[1:]
            else:
                values = [None] * len(records)
            for record, value in zip(records, values, strict=True):
                record[col.key] = value.item() if hasattr(value, "item") else value
        return records


class RowTable(widgets.VBox):
    """An editable table of rows with live computed outputs.

    Parameters
    ----------
    columns : list of Column
        Left to right. Input columns (ChoiceColumn, NumberColumn, TextColumn, or your own
        InputColumn subclass) are edited by the user; OutputColumn and NodeColumn are filled
        in by `compute`.
    compute : callable(TableInputs) -> dict
        Returns {column key: values} in base units: n values for each OutputColumn and n + 1
        for each NodeColumn (including both ends). Extra keys are kept in the results. Raise
        ValueError("message") to show a message instead of results.
    rows : list of dict, optional
        Initial rows as {input column key: value in the starting display units}; missing keys
        use the column default. Defaults to `min_rows` rows of defaults (at least one).
    edges : dict, optional
        Initial NodeColumn boundary values {key: (first, last)} in display units; None keeps
        the column default.
    parameters : list of InputColumn, optional
        Table-wide inputs shown above the table; `params` gives their initial display values.
    unit_systems : dict or list of UnitSystem, optional
        With more than one, a toggle is shown. Values are stored in base units, so switching
        only changes what is displayed.
    units : str, optional
        Name of the starting unit system (default: the first).
    leading_label : str
        Text in the leading row above the first element (shown when there is a NodeColumn).
    item_name : str
        What a row is called, for "Add <item>" and "Remove <item>".
    min_rows : int
        Rows that can't be removed (at least 1 when there is a NodeColumn).
    removable : bool
        Show the ✕ column.
    summary : callable(TableResults) -> str, optional
        HTML shown under the table after each recompute.
    output_quantities : dict, optional
        {extra output key: quantity name}, so ``results.display(key)`` converts extra outputs.
    persist : str, optional
        Save the inputs (rows, boundary values, parameters and unit system) whenever they
        change, under this key, and restore them the next time a table with the same key is
        created. `rows`, `edges`, `params` and `units` are then the *initial* values, used
        only when nothing usable has been saved, and by the Reset button. None (the default)
        always starts from the initial values. The environment variable
        IPYROWTABLE_PERSIST=off turns saving off for every table.
    persist_file : str or Path, optional
        Where to save. Default: `<notebook name>.ipyrowtable.json` beside the notebook, or
        `ipyrowtable.json` in the working directory if the notebook can't be identified.

    Attributes
    ----------
    results : TableResults or None
        The latest results; None while the inputs are invalid.
    error : Exception or None
        Why the latest recompute failed, if it did.
    grid, add_button, message, units_toggle : widgets
        Sub-widgets, e.g. for styling. `units_toggle` is None with a single unit system.
    reset_button, persist_note : widgets
        Shown when saving is on; None otherwise.
    persist_file : Path or None
        The file inputs are saved to, when saving is on.
    """

    REMOVE_WIDTH = "34px"

    def __init__(
        self,
        columns,
        compute,
        *,
        rows=None,
        edges=None,
        parameters=(),
        params=None,
        unit_systems=None,
        units=None,
        leading_label="",
        item_name="row",
        min_rows=1,
        removable=True,
        summary=None,
        output_quantities=None,
        persist=None,
        persist_file=None,
    ):
        super().__init__()
        self._loading = True  # no saving while the table is being built
        self.add_class("ipyrowtable")
        self.columns = list(columns)
        _check_columns(self.columns)
        self.compute = compute
        self.removable = removable
        self.results = None
        self.error = None
        self.callback_error = None
        self._summary_fn = summary
        self._callbacks = []
        self._syncing = False  # True while a unit change rewrites the inputs
        self._rows = []

        if unit_systems is None:
            unit_systems = {"default": UnitSystem("default")}
        elif not isinstance(unit_systems, dict):
            unit_systems = {system.name: system for system in unit_systems}
        self.unit_systems = dict(unit_systems)
        u = self._units = self.unit_systems[units or next(iter(self.unit_systems))]

        self._inputs = [c for c in self.columns if isinstance(c, InputColumn)]
        self._outputs = [c for c in self.columns if isinstance(c, OutputColumn)]
        self._nodes = [c for c in self.columns if isinstance(c, NodeColumn)]
        self._params = list(parameters)
        self.min_rows = max(min_rows, 1 if self._nodes else 0)
        self._quantities = {c.key: c.quantity for c in self.columns + self._params if c.quantity}
        self._quantities.update(output_quantities or {})
        self._item_name = item_name

        children = []

        # ---- unit toggle
        self.units_toggle = None
        if len(self.unit_systems) > 1:
            self.units_toggle = widgets.ToggleButtons(
                options=list(self.unit_systems), value=u.name, description="Units:",
                style={"button_width": "90px"},
            )
            self.units_toggle.add_class("ipyrowtable-units")
            self.units_toggle.observe(self._on_units_toggle, names="value")
            children.append(self.units_toggle)

        # ---- parameters
        params = params or {}
        unknown = set(params) - {c.key for c in self._params}
        if unknown:
            raise KeyError(f"Unknown parameter(s): {sorted(unknown)}")
        self._param_values, self._param_widgets, self._param_labels = {}, {}, {}
        boxes = []
        for col in self._params:
            value = col.to_base(params[col.key], u) if col.key in params else col.default_value(u)
            self._param_values[col.key] = value
            w = col.create_widget(value, u)
            w.add_class(f"ipyrowtable-param-{col.key}")
            w.observe(lambda ch, c=col: self._on_param(c, ch.new), names="value")
            label = widgets.HTML()
            self._param_widgets[col.key], self._param_labels[col.key] = w, label
            boxes.append(widgets.HBox(
                [label, widgets.Box([w], layout=widgets.Layout(width=col.width))],
                layout=widgets.Layout(margin="0 24px 4px 0", align_items="center"),
            ))
        if boxes:
            children.append(widgets.HBox(boxes, layout=widgets.Layout(flex_flow="row wrap")))

        # ---- boundary values of node columns
        edges = edges or {}
        unknown = set(edges) - {c.key for c in self._nodes}
        if unknown:
            raise KeyError(f"Unknown NodeColumn(s) in edges: {sorted(unknown)}")
        self._edge_values, self._edge_widgets, self._leading_outputs = {}, {}, {}
        for col in self._nodes:
            given = (tuple(edges.get(col.key) or ()) + (None, None))[:2]
            values, ends = [], {}
            for end, spec in zip(_ENDS, given, strict=True):
                value = widget = None
                if end in col.inputs:
                    number = col.ends[end]
                    value = number.default_value(u) if spec is None else number.to_base(spec, u)
                    widget = number.create_widget(value, u)
                    widget.add_class(f"ipyrowtable-{col.key}-{end}")
                    widget.observe(
                        lambda ch, c=col, e=end: self._on_edge(c, e, ch.new), names="value"
                    )
                values.append(value)
                ends[end] = widget
            self._edge_values[col.key], self._edge_widgets[col.key] = values, ends
            if ends["first"] is None:
                self._leading_outputs[col.key] = widgets.HTML()
                self._leading_outputs[col.key].add_class(f"ipyrowtable-{col.key}")

        # ---- header and leading row
        self._headers = {c.key: widgets.HTML() for c in self.columns}
        for header in self._headers.values():
            header.add_class("ipyrowtable-header")
        self._corner = [widgets.HTML(), widgets.HTML()] if removable else []
        self._leading = []
        if self._nodes:
            label_col = next((c for c in self.columns if not isinstance(c, NodeColumn)), None)
            for col in self.columns:
                if isinstance(col, NodeColumn):
                    cell = self._edge_widgets[col.key]["first"] or self._leading_outputs[col.key]
                elif col is label_col and leading_label:
                    cell = widgets.HTML(f"<i style='color:gray'>{html.escape(leading_label)}</i>")
                else:
                    cell = widgets.HTML()
                self._leading.append(cell)

        # ---- grid, add button, message line
        widths = ([self.REMOVE_WIDTH] if removable else []) + [c.width for c in self.columns]
        self.grid = widgets.GridBox(layout=widgets.Layout(
            grid_template_columns=" ".join(widths), grid_gap="4px 10px", align_items="center",
        ))
        self.grid.add_class("ipyrowtable-grid")
        self.add_button = widgets.Button(description=f"Add {item_name}", icon="plus")
        self.add_button.add_class("ipyrowtable-add")
        self.add_button.on_click(lambda _: self.add_row())
        self.message = widgets.HTML()
        self.message.add_class("ipyrowtable-message")

        self.persist_key = persist if persist and persistence_enabled() else None
        self._store = None
        self.reset_button = self.persist_note = None
        buttons = [self.add_button]
        if self.persist_key:
            self._store = StateFile(persist_file if persist_file else default_state_file())
            self.reset_button = widgets.Button(
                description="Reset", icon="undo", tooltip="Go back to the initial values"
            )
            self.reset_button.add_class("ipyrowtable-reset")
            self.reset_button.on_click(self._on_reset_click)
            self._reset_armed = False
            buttons.append(self.reset_button)
            self.persist_note = widgets.HTML()
            self.persist_note.add_class("ipyrowtable-persist")
        self._backup_pending = False
        self.children = children + [
            self.grid,
            widgets.HBox(buttons) if len(buttons) > 1 else self.add_button,
            self.message,
            *([self.persist_note] if self.persist_note is not None else []),
        ]

        if rows is None:
            rows = [{}] * max(self.min_rows, 1)
        elif len(rows) < self.min_rows:
            raise ValueError(f"Need at least {self.min_rows} row(s); got {len(rows)}.")
        for values in rows:
            self._append_row(values)
        self._update_labels()
        self._rebuild()

        self._initial_state = copy.deepcopy(self.get_inputs())
        if self._store is not None:
            self._restore()
        self._loading = False

    # ----------------------------------------------------------------- public API

    @property
    def units(self) -> UnitSystem:
        """The current UnitSystem. Assign a unit-system name to switch (same as the toggle)."""
        return self._units

    @units.setter
    def units(self, name):
        name = getattr(name, "name", name)
        if name not in self.unit_systems:
            raise KeyError(f"Unknown unit system {name!r}; have {list(self.unit_systems)}")
        if self.units_toggle is not None:
            self.units_toggle.value = name
        else:
            self._set_units(name)

    def __len__(self):
        return len(self._rows)

    def add_row(self, values=None) -> int:
        """Append a row and return its index.

        `values` maps input column keys to values in the current display units; missing
        keys use the column defaults.
        """
        self._append_row(values)
        self._rebuild()
        return len(self._rows) - 1

    def add_rows(self, rows) -> None:
        """Append several rows (each a dict like `add_row` takes), recomputing once."""
        for values in rows:
            self._append_row(values)
        self._rebuild()

    def _append_row(self, values):
        """Append a row given display-unit values (missing keys use defaults)."""
        u = self._units
        values = values or {}
        unknown = set(values) - {c.key for c in self._inputs}
        if unknown:
            raise KeyError(f"Unknown input column(s): {sorted(unknown)}")
        self._append_row_base({
            c.key: c.to_base(values[c.key], u) if c.key in values else c.default_value(u)
            for c in self._inputs
        })

    def _append_row_base(self, base_values):
        """Append a row given a complete dict of base-unit values."""
        u = self._units
        row = {"values": {}, "widgets": {}, "outputs": {}}
        for col in self._inputs:
            value = base_values[col.key]
            widget = col.create_widget(value, u)
            widget.add_class(f"ipyrowtable-{col.key}")
            widget.observe(lambda ch, r=row, c=col: self._on_row_input(r, c, ch.new), names="value")
            row["values"][col.key], row["widgets"][col.key] = value, widget
        for col in self._outputs:
            row["outputs"][col.key] = widgets.HTML()
            row["outputs"][col.key].add_class(f"ipyrowtable-{col.key}")
        row["remove"] = widgets.Button(
            description="✕",
            tooltip=f"Remove {self._item_name}",
            layout=widgets.Layout(width="32px"),
        )
        row["remove"].add_class("ipyrowtable-remove")
        row["remove"].on_click(lambda _, r=row: self.remove_row(r))
        self._rows.append(row)

    def remove_row(self, row) -> bool:
        """Remove a row by index (0 = top). Returns False if only `min_rows` rows remain."""
        if isinstance(row, int):
            row = self._rows[row]
        if len(self._rows) <= self.min_rows:
            return False
        self._rows.remove(row)
        _close_row(row)
        self._rebuild()
        return True

    @property
    def rows(self) -> list[dict]:
        """The input rows as dicts of display-unit values, top to bottom."""
        return [
            {c.key: c.to_display(r["values"][c.key], self._units) for c in self._inputs}
            for r in self._rows
        ]

    @property
    def params(self) -> dict:
        """Parameter values in display units."""
        return {c.key: c.to_display(self._param_values[c.key], self._units) for c in self._params}

    def cell(self, row: int, key: str):
        """The widget shown for column `key` in row `row` (an input box or an output HTML).

        For a NodeColumn with an editable last end, the last row's cell is that input.
        """
        r = self._rows[row]
        if key in r["widgets"]:
            return r["widgets"][key]
        last = self._edge_widgets.get(key, {}).get("last")
        if last is not None and r is self._rows[-1]:
            return last
        return r["outputs"][key]

    def param_widget(self, key: str):
        """The input widget for a parameter."""
        return self._param_widgets[key]

    def edge_widget(self, key: str, end: str = "first"):
        """The input widget for one end ("first" or "last") of a NodeColumn, or None if that
        end is an output."""
        return self._edge_widgets[key][end]

    def on_update(self, callback):
        """Call callback(results) after every change; results is None while inputs are invalid.

        The callback is also called once right away.
        """
        self._callbacks.append(callback)
        callback(self.results)

    def recompute(self):
        """Run compute again, e.g. after changing data your compute function reads."""
        self._recompute()

    # ----------------------------------------------------------------- state

    def get_inputs(self) -> dict:
        """A JSON-ready snapshot of the inputs, in base units.

        {"units": name, "rows": [{key: value}], "edges": {key: [first, last]},
        "params": {key: value}}; an end of a NodeColumn that isn't an input is None.
        """
        return {
            "units": self._units.name,
            "rows": [{k: _plain(v) for k, v in r["values"].items()} for r in self._rows],
            "edges": {k: [_plain(v) for v in values] for k, values in self._edge_values.items()},
            "params": {k: _plain(v) for k, v in self._param_values.items()},
        }

    def set_inputs(self, state: dict) -> None:
        """Load a snapshot from `get_inputs` (or a saved file).

        Keys for columns that no longer exist are ignored, and missing ones get defaults.
        Raises ValueError, leaving the table unchanged, if a value can't be used.
        """
        self._apply_state(self._validate_state(state))

    def reset(self) -> None:
        """Go back to the initial rows, boundary values, parameters and unit system."""
        self._apply_state(copy.deepcopy(self._initial_state))
        if self.persist_note is not None:
            self._note("Reset to the initial values.")

    @property
    def persist_file(self) -> Path | None:
        return self._store.path if self._store is not None else None

    # ----------------------------------------------------------------- event handlers

    def _on_row_input(self, row, col, value):
        if not self._syncing:
            row["values"][col.key] = col.to_base(value, self._units)
            self._recompute()

    def _on_param(self, col, value):
        if not self._syncing:
            self._param_values[col.key] = col.to_base(value, self._units)
            self._recompute()

    def _on_edge(self, col, end, value):
        if not self._syncing:
            self._edge_values[col.key][_ENDS.index(end)] = col.ends[end].to_base(value, self._units)
            self._recompute()

    def _on_units_toggle(self, change):
        if not self._syncing:
            self._set_units(change.new)

    def _set_units(self, name):
        self._units = self.unit_systems[name]
        self._refresh_widgets()
        self._update_labels()
        self._recompute()

    def _refresh_widgets(self):
        """Show every stored (base) value in its widget, in the current units."""
        u = self._units
        self._syncing = True
        try:
            if self.units_toggle is not None:
                self.units_toggle.value = u.name
            for row in self._rows:
                for col in self._inputs:
                    col.refresh(row["widgets"][col.key], row["values"][col.key], u)
            for col in self._params:
                col.refresh(self._param_widgets[col.key], self._param_values[col.key], u)
            for col in self._nodes:
                for index, end in enumerate(_ENDS):
                    widget = self._edge_widgets[col.key][end]
                    if widget is not None:
                        col.ends[end].refresh(widget, self._edge_values[col.key][index], u)
        finally:
            self._syncing = False

    def _validate_state(self, state) -> dict:
        """Check a snapshot and fill gaps; returns a complete snapshot or raises ValueError."""
        if not isinstance(state, dict):
            raise ValueError("the saved inputs aren't a table")
        name = state.get("units")  # an unknown or missing unit system means the initial one
        units = self.unit_systems.get(name) or self.unit_systems[self._initial_state["units"]]
        rows = state.get("rows")
        if not isinstance(rows, list):
            raise ValueError("the saved inputs have no list of rows")
        if len(rows) < max(self.min_rows, 1):
            raise ValueError(f"need at least {max(self.min_rows, 1)} row(s), found {len(rows)}")
        clean_rows = []
        for i, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"row {i} isn't a set of column values")
            clean = {}
            for col in self._inputs:
                try:
                    clean[col.key] = (col.validate(row[col.key]) if col.key in row
                                      else col.default_value(units))
                except ValueError as exc:
                    raise ValueError(f"row {i}, {exc}") from None
            clean_rows.append(clean)

        saved_edges = state.get("edges") or {}
        if not isinstance(saved_edges, dict):
            raise ValueError("the saved boundary values aren't a mapping")
        clean_edges = {}
        for col in self._nodes:
            given = saved_edges.get(col.key)
            if given is not None and (not isinstance(given, list) or len(given) != 2):
                raise ValueError(f"{col.key}: expected [first, last] boundary values")
            values = []
            for index, end in enumerate(_ENDS):
                if end not in col.inputs:
                    values.append(None)
                elif given is None or given[index] is None:
                    values.append(col.ends[end].default_value(units))
                else:
                    values.append(col.ends[end].validate(given[index]))
            clean_edges[col.key] = values

        saved_params = state.get("params") or {}
        if not isinstance(saved_params, dict):
            raise ValueError("the saved parameters aren't a mapping")
        clean_params = {
            col.key: (col.validate(saved_params[col.key]) if col.key in saved_params
                      else col.default_value(units))
            for col in self._params
        }
        return {"units": units.name, "rows": clean_rows, "edges": clean_edges,
                "params": clean_params}

    def _apply_state(self, state):
        """Replace everything with a validated snapshot, then lay out and recompute."""
        self._units = self.unit_systems[state["units"]]
        for row in self._rows:
            _close_row(row)
        self._rows = []
        for values in state["rows"]:
            self._append_row_base(values)
        for key, values in state["edges"].items():
            self._edge_values[key] = list(values)
        self._param_values.update(state["params"])
        self._refresh_widgets()
        self._update_labels()
        self._rebuild()

    # ----------------------------------------------------------------- saving

    def _restore(self):
        where = self._file_label()
        try:
            saved = self._store.load(self.persist_key)
            if saved is None:
                self._note(f"Inputs will be saved to {where} as “{html.escape(self.persist_key)}”.")
                return
            self._apply_state(self._validate_state(saved))
        except (StateFileError, ValueError) as exc:
            self._backup_pending = True
            self._note(f"Couldn't restore the saved inputs ({html.escape(str(exc))}), so the "
                       "table starts from its initial values. The old file will be kept as a "
                       ".bak copy when you make a change.", warning=True)
            return
        when = saved.get("saved", "")
        when = f" (saved {html.escape(when[:16].replace('T', ' '))})" if when else ""
        self._note(f"Restored your saved inputs from {where}{when}.")

    def _autosave(self):
        if self._store is None or self._loading:
            return
        try:
            if self._backup_pending:
                backup = self._store.backup()
                self._backup_pending = False
                kept = f" The old file was kept as {html.escape(backup.name)}." if backup else ""
            else:
                kept = ""
            saved = self._store.save(self.persist_key, self.get_inputs())
        except Exception as exc:
            self._note(f"Couldn't save inputs: {html.escape(f'{type(exc).__name__}: {exc}')}",
                       warning=True)
            return
        self._note(f"Saved to {self._file_label()} at {saved[11:19]}.{kept}")

    def _file_label(self):
        path = self._store.path
        return f"<span title='{html.escape(str(path))}'>{html.escape(path.name)}</span>"

    def _note(self, text, warning=False):
        color = "#b9770e" if warning else "gray"
        self.persist_note.value = f"<span style='color:{color}; font-size:0.85em'>{text}</span>"

    def _on_reset_click(self, _):
        if not self._reset_armed:
            self._reset_armed = True
            self.reset_button.description = "Confirm reset"
            self.reset_button.button_style = "warning"
            return
        self.reset()

    def _disarm_reset(self):
        if self.reset_button is not None and self._reset_armed:
            self._reset_armed = False
            self.reset_button.description = "Reset"
            self.reset_button.button_style = ""

    # ----------------------------------------------------------------- internals

    def _update_labels(self):
        for col in self.columns:
            self._headers[col.key].value = f"<b>{col.header_text(self._units)}</b>"
        for col in self._params:
            self._param_labels[col.key].value = col.header_text(self._units)

    def _rebuild(self):
        """Lay out the grid. For a NodeColumn with an editable last end, the last row shows it."""
        cells = self._corner[:1] + [self._headers[c.key] for c in self.columns]
        if self._nodes:
            cells += self._corner[1:] + self._leading
        last = len(self._rows) - 1
        for i, row in enumerate(self._rows):
            if self.removable:
                row["remove"].disabled = len(self._rows) <= self.min_rows
                cells.append(row["remove"])
            for col in self.columns:
                if isinstance(col, InputColumn):
                    cells.append(row["widgets"][col.key])
                elif (isinstance(col, NodeColumn) and i == last
                      and self._edge_widgets[col.key]["last"] is not None):
                    cells.append(self._edge_widgets[col.key]["last"])
                else:
                    cells.append(row["outputs"][col.key])
        self.grid.children = cells
        self._recompute()

    def _recompute(self):
        u = self._units
        n = len(self._rows)
        inputs = TableInputs(
            rows=[dict(r["values"]) for r in self._rows],
            edges={key: tuple(values) for key, values in self._edge_values.items()},
            params=dict(self._param_values),
        )
        try:
            outputs = dict(self.compute(inputs) or {})
            results = TableResults(inputs, outputs, u, self._quantities, tuple(self.columns))
            for col in self._outputs:
                values = outputs.get(col.key)
                is_node = isinstance(col, NodeColumn)
                if values is not None and len(values) != n + is_node:
                    raise ValueError(
                        f"compute returned {len(values)} values for {col.key!r}; "
                        f"expected {n + is_node}."
                    )
                if is_node and col.key in self._leading_outputs:
                    self._leading_outputs[col.key].value = (
                        "" if values is None else col.render(values[0], u)
                    )
                row_values = values[1:] if (is_node and values is not None) else values
                for i, row in enumerate(self._rows):
                    row["outputs"][col.key].value = (
                        "" if values is None else col.render(row_values[i], u)
                    )
            self.results, self.error = results, None
            self.message.value = self._summary_fn(results) if self._summary_fn else ""
        except Exception as exc:  # show the problem in the table rather than a hidden traceback
            self._show_error(exc)
        self._notify()
        self._disarm_reset()
        self._autosave()

    def _show_error(self, exc):
        self.results, self.error = None, exc
        dash = right_aligned("—")
        for row in self._rows:
            for widget in row["outputs"].values():
                widget.value = dash
        for widget in self._leading_outputs.values():
            widget.value = dash
        text = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"
        self.message.value = f"<span style='color:#c0392b'>{html.escape(text)}</span>"

    def _notify(self):
        self.callback_error = None
        for callback in self._callbacks:
            try:
                callback(self.results)
            except Exception as exc:
                self.callback_error = exc
                self.message.value += (
                    "<br><span style='color:#c0392b'>Update callback failed: "
                    f"{html.escape(f'{type(exc).__name__}: {exc}')}</span>"
                )


def _close_row(row):
    for widget in [*row["widgets"].values(), *row["outputs"].values(), row["remove"]]:
        widget.close()


def _plain(value):
    """numpy scalars to Python ones, so snapshots are JSON-ready."""
    return value.item() if hasattr(value, "item") else value


def _check_columns(columns):
    for col in columns:
        if not isinstance(col, Column):
            raise TypeError(f"{col!r} is not a Column.")
    keys = [c.key for c in columns]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"Duplicate column key(s): {duplicates}")
