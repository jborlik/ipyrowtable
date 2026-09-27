"""Saving table inputs to a JSON file between sessions.

A notebook's kernel can't write the notebook's own metadata (only the front end can, and
front ends differ), so inputs are kept in a small JSON file instead, by default next to the
notebook: ``<notebook name>.ipyrowtable.json``. One file holds any number of tables, each
under its own key:

    {
      "ipyrowtable": 1,
      "tables": {
        "pipes": {
          "saved": "2026-09-27T13:10:42-07:00",
          "units": "Metric",
          "rows": [{"material": "Commercial steel", "length": 25.0, "diameter": 0.065}],
          "edges": {"pressure": [400000.0, null]},
          "params": {"flow": 0.005556}
        }
      }
    }

Values are in base units (the units your compute function uses), so they don't depend on
which unit system was showing. Set the environment variable IPYROWTABLE_PERSIST=off to turn
saving and restoring off everywhere, e.g. for batch runs that must start from known inputs.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path

__all__ = [
    "FORMAT_VERSION",
    "StateFile",
    "StateFileError",
    "default_state_file",
    "notebook_path",
    "persistence_enabled",
]

FORMAT_VERSION = 1
ENV_SWITCH = "IPYROWTABLE_PERSIST"
_OFF = {"0", "off", "false", "no"}


class StateFileError(Exception):
    """The state file exists but can't be used."""


def persistence_enabled() -> bool:
    """False when the environment variable IPYROWTABLE_PERSIST is 0, off, false or no."""
    return os.environ.get(ENV_SWITCH, "").strip().lower() not in _OFF


def notebook_path() -> Path | None:
    """Best guess at the running notebook's file, or None.

    VS Code puts the path in the kernel's `__vsc_ipynb_file__` variable; Jupyter Server sets
    the JPY_SESSION_NAME environment variable for the kernels it starts.
    """
    try:
        from IPython import get_ipython

        shell = get_ipython()
        if shell is not None:
            path = shell.user_ns.get("__vsc_ipynb_file__")
            if path:
                return Path(path)
    except Exception:  # pragma: no cover - IPython missing or unusual
        pass
    session = os.environ.get("JPY_SESSION_NAME")
    if session:
        path = Path(session)
        if path.is_absolute() and path.exists():
            return path
        candidate = Path.cwd() / path.name  # the kernel usually runs in the notebook's folder
        if candidate.exists():
            return candidate
    return None


def default_state_file() -> Path:
    """`<notebook name>.ipyrowtable.json` beside the notebook, or `ipyrowtable.json` in the
    working directory when the notebook can't be identified."""
    notebook = notebook_path()
    if notebook is not None and notebook.suffix == ".ipynb":
        return notebook.with_name(f"{notebook.stem}.ipyrowtable.json")
    return Path.cwd() / "ipyrowtable.json"


class StateFile:
    """A JSON file holding the saved inputs of one or more tables."""

    def __init__(self, path):
        self.path = Path(path)

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"ipyrowtable": FORMAT_VERSION, "tables": {}}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateFileError(f"{self.path.name} can't be read ({exc})") from exc
        if not isinstance(data, dict) or not isinstance(data.get("tables"), dict):
            raise StateFileError(f"{self.path.name} isn't an ipyrowtable file")
        version = data.get("ipyrowtable")
        if not isinstance(version, int) or version > FORMAT_VERSION:
            raise StateFileError(
                f"{self.path.name} was saved in format {version!r}, newer than this "
                f"version of ipyrowtable understands ({FORMAT_VERSION})"
            )
        return data

    def load(self, key: str) -> dict | None:
        """The saved state for `key`, or None if there isn't one.

        Raises StateFileError if the file exists but can't be used.
        """
        return self._read()["tables"].get(key)

    def save(self, key: str, state: dict) -> str:
        """Store `state` under `key`, keeping other tables' entries. Returns the timestamp.

        An unusable existing file is replaced; call `backup()` first to keep a copy.
        """
        try:
            data = self._read()
        except StateFileError:
            data = {"ipyrowtable": FORMAT_VERSION, "tables": {}}
        saved = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        data["ipyrowtable"] = FORMAT_VERSION
        data["tables"][key] = {"saved": saved, **state}
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash never leaves a half-written file
        return saved

    def backup(self) -> Path | None:
        """Copy the file to `<name>.bak` (if it exists) and return the copy's path."""
        if not self.path.exists():
            return None
        target = self.path.with_name(self.path.name + ".bak")
        shutil.copy2(self.path, target)
        return target

    def remove(self, key: str) -> bool:
        """Forget the saved state for `key`. Returns True if there was one."""
        data = self._read()
        if key not in data["tables"]:
            return False
        del data["tables"][key]
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, self.path)
        return True
