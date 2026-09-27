"""Saving inputs between sessions, and falling back to the initial values."""

import json

import pytest

from ipyrowtable import NumberColumn, OutputColumn, RowTable
from ipyrowtable.persistence import (
    FORMAT_VERSION,
    StateFile,
    StateFileError,
    default_state_file,
    notebook_path,
    persistence_enabled,
)
from tests.helpers import make_cable, make_wall, text


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / "inputs.json"


def saved(path, key="wall"):
    return json.loads(path.read_text(encoding="utf-8"))["tables"][key]


def edit(wall):
    """Some user edits touching every kind of input."""
    wall.cell(0, "thickness").value = 25.0
    wall.cell(1, "material").value = "brick"
    wall.edge_widget("T", "last").value = -5.0
    wall.add_row({"material": "foam", "thickness": 30.0})
    wall.units = "US"


# --------------------------------------------------------------------------- off by default


def test_off_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wall = make_wall()
    edit(wall)
    assert wall.persist_file is None and wall.reset_button is None
    assert list(tmp_path.iterdir()) == []


def test_environment_switch_turns_it_off(state_file, monkeypatch):
    monkeypatch.setenv("IPYROWTABLE_PERSIST", "off")
    wall = make_wall(persist="wall", persist_file=state_file)
    edit(wall)
    assert not state_file.exists()
    assert wall.persist_key is None and wall.persist_note is None


@pytest.mark.parametrize("value", ["0", "off", "False", "NO"])
def test_environment_switch_values(value, monkeypatch):
    monkeypatch.setenv("IPYROWTABLE_PERSIST", value)
    assert not persistence_enabled()


def test_environment_switch_other_values_leave_it_on(monkeypatch):
    monkeypatch.setenv("IPYROWTABLE_PERSIST", "1")
    assert persistence_enabled()


# --------------------------------------------------------------------------- saving


class TestSaving:
    def test_nothing_is_written_until_something_changes(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        assert not state_file.exists()
        assert "will be saved to inputs.json" in text(wall.persist_note)

    def test_every_change_is_saved_in_base_units(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        edit(wall)
        entry = saved(state_file)
        assert entry["units"] == "US"
        assert entry["rows"] == [
            {"material": "steel", "thickness": pytest.approx(0.025)},
            {"material": "brick", "thickness": pytest.approx(0.05)},
            {"material": "foam", "thickness": pytest.approx(0.03)},
        ]
        assert entry["edges"] == {"T": [100.0, -5.0]}
        assert entry["saved"]
        assert "Saved to inputs.json" in text(wall.persist_note)

    def test_file_format(self, state_file):
        make_wall(persist="wall", persist_file=state_file).add_row()
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["ipyrowtable"] == FORMAT_VERSION
        assert set(data["tables"]["wall"]) == {"saved", "units", "rows", "edges", "params"}

    def test_parameters_and_first_only_boundaries(self, state_file):
        cable = make_cable(persist="cable", persist_file=state_file)
        cable.param_widget("current").value = 20.0
        cable.edge_widget("V", "first").value = 240.0
        entry = saved(state_file, "cable")
        assert entry["params"] == {"current": 20.0}
        assert entry["edges"] == {"V": [240.0, None]}
        assert entry["rows"][0]["name"] == "a"

    def test_invalid_inputs_are_still_saved(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        wall.cell(0, "thickness").value = 0.0
        assert wall.results is None
        assert saved(state_file)["rows"][0]["thickness"] == 0.0

    def test_several_tables_share_a_file(self, state_file):
        make_wall(persist="one", persist_file=state_file).add_row()
        make_cable(persist="two", persist_file=state_file).add_row()
        tables = json.loads(state_file.read_text(encoding="utf-8"))["tables"]
        assert set(tables) == {"one", "two"}
        assert len(tables["one"]["rows"]) == 3

    def test_creates_missing_folders(self, tmp_path):
        target = tmp_path / "inputs" / "design" / "state.json"
        make_wall(persist="wall", persist_file=target).add_row()
        assert target.exists()

    def test_write_failure_is_reported_not_raised(self, tmp_path):
        folder = tmp_path / "a_folder"
        folder.mkdir()
        wall = make_wall(persist="wall", persist_file=folder)  # can't write a file there
        wall.add_row()
        assert "Couldn't save inputs" in text(wall.persist_note)
        assert wall.results is not None

    def test_no_temporary_files_left_behind(self, state_file):
        make_wall(persist="wall", persist_file=state_file).add_row()
        assert [p.name for p in state_file.parent.iterdir()] == ["inputs.json"]


# --------------------------------------------------------------------------- restoring


class TestRestoring:
    def test_new_session_gets_everything_back(self, state_file):
        first = make_wall(persist="wall", persist_file=state_file)
        edit(first)
        second = make_wall(persist="wall", persist_file=state_file)
        assert second.get_inputs() == first.get_inputs()
        assert second.units.name == "US" and second.units_toggle.value == "US"
        assert second.rows == first.rows
        assert second.edge_widget("T", "last").value == first.edge_widget("T", "last").value
        assert second.results["q"] == pytest.approx(first.results["q"])
        assert "Restored your saved inputs from inputs.json" in text(second.persist_note)
        assert second.grid.children[-1] is second.edge_widget("T", "last")

    def test_restoring_does_not_rewrite_the_file(self, state_file):
        edit(make_wall(persist="wall", persist_file=state_file))
        before = state_file.read_text(encoding="utf-8")
        make_wall(persist="wall", persist_file=state_file)
        assert state_file.read_text(encoding="utf-8") == before

    def test_parameters_restored(self, state_file):
        make_cable(persist="cable", persist_file=state_file).param_widget("current").value = 7.0
        again = make_cable(persist="cable", persist_file=state_file)
        assert again.params == {"current": 7.0}
        assert again.param_widget("current").value == 7.0

    def test_initial_values_used_when_nothing_is_saved(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file,
                         rows=[{"material": "brick", "thickness": 120.0}])
        assert wall.rows == [{"material": "brick", "thickness": 120.0}]

    def test_other_keys_do_not_interfere(self, state_file):
        edit(make_wall(persist="other", persist_file=state_file))
        wall = make_wall(persist="wall", persist_file=state_file)
        assert len(wall) == 2 and wall.units.name == "metric"

    def test_saved_inputs_win_over_changed_initial_values(self, state_file):
        make_wall(persist="wall", persist_file=state_file).add_row()
        wall = make_wall(persist="wall", persist_file=state_file,
                         rows=[{"material": "brick", "thickness": 1.0}])
        assert len(wall) == 3


# --------------------------------------------------------------------------- unusable saves


def write(path, data):
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def entry(**changes):
    base = {"units": "metric", "rows": [{"material": "steel", "thickness": 0.01}],
            "edges": {"T": [100.0, 20.0]}, "params": {}}
    base.update(changes)
    return {"ipyrowtable": 1, "tables": {"wall": base}}


class TestFallback:
    @pytest.mark.parametrize(
        ("contents", "reason"),
        [
            ("{not json", "can't be read"),
            ('["a", "list"]', "isn't an ipyrowtable file"),
            ({"ipyrowtable": 99, "tables": {}}, "newer than this version"),
            (entry(rows=[{"material": "unobtainium", "thickness": 0.01}]), "not one of the"),
            (entry(rows=[{"material": "steel", "thickness": "thick"}]), "expected a number"),
            (entry(rows=[{"material": "steel", "thickness": -1.0}]), "below the minimum"),
            (entry(rows=[]), "need at least 1 row"),
            (entry(rows="nope"), "no list of rows"),
            (entry(rows=["nope"]), "isn't a set of column values"),
            (entry(edges={"T": [1.0]}), "expected [first, last]"),
            (entry(edges={"T": ["hot", 1.0]}), "expected a number"),
        ],
    )
    def test_falls_back_to_initial_values(self, state_file, contents, reason):
        write(state_file, contents)
        wall = make_wall(persist="wall", persist_file=state_file)
        assert wall.rows == [{"material": "steel", "thickness": 10.0},
                             {"material": "foam", "thickness": 50.0}]
        note = text(wall.persist_note)
        assert "Couldn't restore the saved inputs" in note and reason in note
        assert wall.results is not None

    def test_bad_file_is_backed_up_before_being_replaced(self, state_file):
        write(state_file, "{not json")
        wall = make_wall(persist="wall", persist_file=state_file)
        assert not state_file.with_name("inputs.json.bak").exists()  # nothing touched yet
        wall.add_row()
        assert state_file.with_name("inputs.json.bak").read_text(encoding="utf-8") == "{not json"
        assert len(saved(state_file)["rows"]) == 3
        assert "kept as inputs.json.bak" in text(wall.persist_note)

    def test_other_tables_survive_a_bad_entry(self, state_file):
        data = entry(rows=[{"material": "unobtainium", "thickness": 0.01}])
        data["tables"]["other"] = {"units": "metric", "rows": [], "edges": {}, "params": {}}
        write(state_file, data)
        make_wall(persist="wall", persist_file=state_file).add_row()
        assert "other" in json.loads(state_file.read_text(encoding="utf-8"))["tables"]

    def test_added_and_removed_columns_are_tolerated(self, state_file):
        # saved before a column was added (no "material") and after one was dropped ("colour")
        write(state_file, entry(rows=[{"thickness": 0.02, "colour": "red"}]))
        wall = make_wall(persist="wall", persist_file=state_file)
        assert wall.rows == [{"material": "steel", "thickness": 20.0}]
        assert "Restored" in text(wall.persist_note)

    def test_unknown_unit_system_uses_the_initial_one(self, state_file):
        write(state_file, entry(units="cgs"))
        wall = make_wall(persist="wall", persist_file=state_file, units="US")
        assert wall.units.name == "US"

    def test_missing_boundaries_and_parameters_use_defaults(self, state_file):
        write(state_file, {"ipyrowtable": 1, "tables": {"cable": {
            "rows": [{"name": "x", "gauge": "10 AWG", "length": 5.0}]}}})
        cable = make_cable(persist="cable", persist_file=state_file)
        assert cable.params == {"current": 15.0}
        assert cable.edge_widget("V", "first").value == 120.0

    def test_values_at_a_bound_survive_unit_round_off(self, tmp_path):
        # -273.15 °C shown in °F and typed back can come out a hair below the bound
        col = NumberColumn("T", quantity="temperature", min=-273.15)
        assert col.validate(-273.15000000000003) == pytest.approx(-273.15)


# --------------------------------------------------------------------------- reset


class TestReset:
    def test_reset_needs_a_second_click(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        edit(wall)
        wall.reset_button.click()
        assert wall.reset_button.description == "Confirm reset"
        assert len(wall) == 3  # nothing happened yet
        wall.reset_button.click()
        assert wall.rows == [{"material": "steel", "thickness": 10.0},
                             {"material": "foam", "thickness": 50.0}]
        assert wall.units.name == "metric" and wall.edge_widget("T", "last").value == 20.0
        assert wall.reset_button.description == "Reset"
        assert text(wall.persist_note) == "Reset to the initial values."
        assert len(saved(state_file)["rows"]) == 2  # and saved

    def test_any_other_change_cancels_a_pending_reset(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        wall.reset_button.click()
        wall.cell(0, "thickness").value = 12.0
        assert wall.reset_button.description == "Reset"
        wall.reset_button.click()
        assert wall.rows[0]["thickness"] == 12.0  # first click again only arms it

    def test_reset_goes_to_initial_values_not_saved_ones(self, state_file):
        edit(make_wall(persist="wall", persist_file=state_file))
        wall = make_wall(persist="wall", persist_file=state_file)
        assert len(wall) == 3
        wall.reset()
        assert len(wall) == 2 and wall.units.name == "metric"

    def test_reset_without_saving(self):
        wall = make_wall()
        edit(wall)
        wall.reset()
        assert len(wall) == 2 and wall.units.name == "metric"


# --------------------------------------------------------------------------- get/set inputs


class TestInputsSnapshot:
    def test_round_trip(self, wall):
        edit(wall)
        snapshot = wall.get_inputs()
        json.dumps(snapshot)  # JSON-ready
        other = make_wall()
        other.set_inputs(snapshot)
        assert other.get_inputs() == snapshot
        assert other.rows == wall.rows

    def test_invalid_snapshot_leaves_the_table_unchanged(self, wall):
        before = wall.get_inputs()
        bad = dict(before, rows=[{"material": "unobtainium", "thickness": 0.01}])
        with pytest.raises(ValueError, match="row 1, material"):
            wall.set_inputs(bad)
        assert wall.get_inputs() == before

    def test_set_inputs_with_persistence_saves(self, state_file):
        wall = make_wall(persist="wall", persist_file=state_file)
        snapshot = wall.get_inputs()
        snapshot["rows"] = snapshot["rows"][:1]
        wall.set_inputs(snapshot)
        assert len(saved(state_file)["rows"]) == 1

    def test_custom_column_values_are_accepted(self):
        from ipyrowtable import InputColumn

        class Anything(InputColumn):
            def create_widget(self, value, units):
                import ipywidgets as widgets

                return widgets.IntText(value=value)

        table = RowTable(columns=[Anything("n", default=1), OutputColumn("y")],
                         compute=lambda inp: {"y": inp.column("n") * 2.0})
        table.set_inputs({"rows": [{"n": 4}, {"n": 5}]})
        assert table.results["y"].tolist() == [8.0, 10.0]


# --------------------------------------------------------------------------- the state file


class TestStateFile:
    def test_missing_file_is_empty(self, state_file):
        assert StateFile(state_file).load("x") is None

    def test_remove(self, state_file):
        store = StateFile(state_file)
        store.save("a", {"rows": []})
        store.save("b", {"rows": []})
        assert store.remove("a") is True and store.remove("a") is False
        assert store.load("a") is None and store.load("b") is not None

    def test_unreadable_file_raises(self, state_file):
        write(state_file, "][")
        with pytest.raises(StateFileError):
            StateFile(state_file).load("x")

    def test_backup_of_missing_file(self, state_file):
        assert StateFile(state_file).backup() is None


class TestDefaultLocation:
    def test_vscode_notebook(self, tmp_path, monkeypatch):
        class Shell:  # VS Code defines __vsc_ipynb_file__ in the kernel's namespace
            user_ns = {"__vsc_ipynb_file__": str(tmp_path / "design.ipynb")}

        monkeypatch.setattr("IPython.get_ipython", lambda: Shell())
        assert default_state_file() == tmp_path / "design.ipyrowtable.json"

    def test_jupyter_server_session(self, tmp_path, monkeypatch):
        (tmp_path / "study.ipynb").write_text("{}")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("IPython.get_ipython", lambda: None)
        monkeypatch.setenv("JPY_SESSION_NAME", "projects/study.ipynb")  # relative to server root
        assert notebook_path() == tmp_path / "study.ipynb"
        assert default_state_file() == tmp_path / "study.ipyrowtable.json"

    def test_fallback_is_the_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("IPython.get_ipython", lambda: None)
        monkeypatch.delenv("JPY_SESSION_NAME", raising=False)
        assert default_state_file() == tmp_path / "ipyrowtable.json"

    def test_table_uses_the_default_location(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("IPython.get_ipython", lambda: None)
        monkeypatch.delenv("JPY_SESSION_NAME", raising=False)
        make_wall(persist="wall").add_row()
        assert (tmp_path / "ipyrowtable.json").exists()


def test_conduction_example_supports_persistence(state_file):
    from ipyrowtable.examples.conduction import LayerStack

    stack = LayerStack(persist="wall", persist_file=state_file)
    stack.cell(0, "thickness").value = 3.0
    again = LayerStack(persist="wall", persist_file=state_file)
    assert again.layers[0] == ("Carbon steel", 3.0)
