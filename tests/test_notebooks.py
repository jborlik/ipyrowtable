"""Run every example notebook top to bottom in a fresh kernel.

This keeps the examples honest: any API change that breaks them fails here.
"""

from pathlib import Path

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
NOTEBOOKS = sorted(EXAMPLES.glob("*.ipynb"))


@pytest.mark.notebooks
@pytest.mark.parametrize("path", NOTEBOOKS, ids=[p.name for p in NOTEBOOKS])
def test_notebook_runs_without_errors(path):
    nb = nbformat.read(path, as_version=4)
    client = nbclient.NotebookClient(
        nb, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(EXAMPLES)}}
    )
    client.execute()  # raises CellExecutionError, with the failing cell, on any error
    errors = [o for cell in nb.cells for o in cell.get("outputs", []) if o.output_type == "error"]
    assert not errors


def test_examples_exist():
    assert NOTEBOOKS, f"no notebooks found in {EXAMPLES}"
