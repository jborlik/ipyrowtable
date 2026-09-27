# Contributing to ipyrowtable

## Setting up

```bash
git clone <your fork> && cd ipyrowtable
python -m venv .venv && source .venv/bin/activate    # or: uv venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests

```bash
pytest                      # the full fast suite, about 30 s
pytest --cov                # with a coverage report
pytest -m "not notebooks"   # skip executing the example notebooks
```

The suite tests at several levels, from pure logic up to a real browser:

| Level | Files | What it checks |
|---|---|---|
| Logic | `test_units_and_formatting.py`, `test_columns.py` | unit conversions, number formatting, column widgets, header templates |
| Widget behavior | `test_table.py`, `test_units_toggle.py`, `test_results_and_errors.py`, `test_figure.py`, `test_persistence.py` | builds real widgets and drives them the way a user does (see below) |
| Invariants | `test_properties.py` | property-based tests (see below) |
| Physics | `test_conduction.py` | the conduction example against independent checks (see below) |
| Examples | `test_notebooks.py` | runs every notebook in `examples/` top to bottom in a fresh kernel |
| Browser | `tests/ui/` | renders the widgets in headless Chromium and uses the mouse and keyboard |

**Widget behavior.** These tests set `widget.value`, which is exactly what typing in a box
does, and call `button.click()`, which runs the same handlers as a mouse click. They then
check what the table shows and stores. No browser or kernel is needed.

**Invariants.** A hypothesis state machine plays random sequences of user actions: add and
remove rows, type thicknesses, pick materials, set boundaries, flip units, and start a "new
session" (a fresh table restoring the saved inputs). After every step it checks:

- the grid layout
- the stored values, against a simple model
- what is displayed
- the physics, against an independent nodal-balance solve

When a sequence fails, hypothesis shrinks it to the shortest one that still fails.

**Physics.** The conduction example is checked against things that don't share code with its
solver:

- Fourier's law for a single layer
- an independent linear-system solve
- symmetry when the stack is reversed
- NIST conversion constants

### Browser tests

`tests/ui/` uses [pytest-ipywidgets](https://solara.dev/documentation/advanced/howto/testing)
(from the Solara project). The widgets live in the test process, a Solara server renders
them with the standard ipywidgets front end, and Playwright drives headless Chromium. These
tests cover what the others can't: that the table renders, and that clicks and keystrokes
reach Python and the results come back to the page.

```bash
pip install -e ".[ui]"
playwright install chromium
pytest -m ui
```

They're excluded from the default run (`-m "not ui"` in `pyproject.toml`) because they need
a browser. The Solara server loads its front-end assets from cdn.jsdelivr.net, so they also
need network access.

### What isn't covered automatically

The browser tests render through Solara's page, not JupyterLab's. Before a release, open the
three notebooks in JupyterLab (and in VS Code, if you support it) and click through them.
Check the column alignment, the units toggle, and that the plot sits beside the table and
wraps below it when the window is narrow.

## Style

```bash
ruff check .
```

## Releasing

1. Update `__version__` in `src/ipyrowtable/__init__.py` and add a section to `CHANGELOG.md`.
2. Build and check:

   ```bash
   rm -rf dist && python -m build && twine check --strict dist/*
   ```

3. Try the wheel in a clean environment:

   ```bash
   python -m venv /tmp/try && /tmp/try/bin/pip install "dist/ipyrowtable-*.whl[test]"
   cd /tmp && /tmp/try/bin/python -m pytest <repo>/tests
   ```

4. Publish:
   - **TestPyPI first:** `twine upload --repository testpypi dist/*`, then
     `pip install -i https://test.pypi.org/simple/ ipyrowtable` in a fresh environment.
   - **Then PyPI**, either with `twine upload dist/*` or by publishing a GitHub release. The
     release route runs `.github/workflows/publish.yml` using PyPI trusted publishing. To set
     that up once, add the repository as a trusted publisher on PyPI, with workflow
     `publish.yml` and environment `pypi`.

### Before the first release

- In `pyproject.toml`, add your name to `authors` and fill in `[project.urls]`.
- PyPI can't show images by relative path. Change the screenshot link in `README.md` to an
  absolute URL, such as `https://raw.githubusercontent.com/<you>/ipyrowtable/main/docs/screenshot.png`.
