# Changelog

## 0.1.2

- Fixed horizontal scrollbars, a few pixels wide, that appeared when nothing needed scrolling.
  Widgets that fill their slot (`width="100%"`) stuck out of it by their CSS margin. This
  affected input boxes in the table's last column when it is shown beside a plot, and the
  parameter boxes above the table.
- `side_by_side` leaves its gap only between items on the same line, so a plot that wraps
  below the table on a narrow screen no longer sticks out to the right. It no longer sets
  the items' margins.
- Fix commented-out URLS in pyproject.toml

## 0.1.1

First release.

- `RowTable`: an editable table with add and remove row buttons, live computed outputs,
  parameters, a summary line, update callbacks, and error messages in place of results.
- Columns: `ChoiceColumn`, `NumberColumn`, `TextColumn`, `OutputColumn`, and `NodeColumn` for
  values between rows with editable boundary conditions.
- `Unit` / `UnitSystem`, with a toggle that changes what is displayed without touching stored
  values.
- `TableResults`, with base and display values and `records()`.
- `LiveFigure` for matplotlib plots that follow the table; `side_by_side` layout helper.
- `ipyrowtable.examples.conduction`: steady conduction through a plane composite wall.
- Saving inputs between sessions: `persist=` and `persist_file=` on `RowTable` (and
  `LayerStack`), with a Reset button, fallback to the initial values when the saved inputs
  can't be used, and `IPYROWTABLE_PERSIST=off` to turn saving off everywhere.
- `get_inputs()` / `set_inputs()` and `reset()` on `RowTable`; `validate()` on input columns.
