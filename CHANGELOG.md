# Changelog

## 0.1.0 (unreleased)

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
