"""The results object, update callbacks, and how failures are reported."""

import numpy as np
import pytest

from ipyrowtable import NumberColumn, OutputColumn, RowTable, TableResults
from tests.helpers import make_cable, text


class TestResults:
    def test_base_values(self, wall):
        r = wall.results
        assert isinstance(r, TableResults)
        np.testing.assert_allclose(r["thickness"], [0.01, 0.05])
        assert list(r["material"]) == ["steel", "foam"]
        assert r["T"][0] == 100.0 and r["T"][-1] == 20.0
        assert r.base("q") == r["q"]

    def test_display_values(self, wall):
        wall.units = "US"
        r = wall.results
        np.testing.assert_allclose(r.display("thickness"), [0.3937008, 1.9685039])
        assert r.display("T")[0] == pytest.approx(212.0)
        assert r.display("material").tolist() == ["steel", "foam"]

    def test_parameters_and_edges(self, cable):
        r = cable.results
        assert r["current"] == 15.0
        assert r.inputs.edges["V"] == (120.0, None)

    def test_contains_and_missing_keys(self, wall):
        assert "q" in wall.results and "thickness" in wall.results
        assert "nope" not in wall.results
        with pytest.raises(KeyError):
            wall.results["nope"]

    def test_records_mirror_the_table(self, wall):
        wall.units = "US"
        records = wall.results.records()
        assert [set(r) for r in records] == [{"material", "thickness", "R", "T"}] * 2
        assert records[0]["material"] == "steel"
        assert records[0]["thickness"] == pytest.approx(0.3937008)
        assert records[-1]["T"] == pytest.approx(68.0)  # value at the bottom face
        assert isinstance(records[0]["R"], float)

    def test_records_in_base_units(self, wall):
        records = wall.results.records(display=False)
        assert records[1]["thickness"] == pytest.approx(0.05)

    def test_records_with_an_output_compute_skipped(self):
        table = RowTable(columns=[NumberColumn("x", default=1.0), OutputColumn("y")],
                         compute=lambda inp: {})
        assert table.results.records() == [{"x": 1.0, "y": None}]
        assert text(table.cell(0, "y")) == ""

    def test_inputs_column_helper(self, cable):
        assert cable.results.inputs.column("gauge").tolist() == ["12 AWG", "14 AWG"]


class TestCallbacks:
    def test_called_on_registration_and_every_change(self, wall):
        seen = []
        wall.on_update(seen.append)
        wall.cell(0, "thickness").value = 20.0
        wall.add_row()
        wall.remove_row(0)
        assert len(seen) == 4
        assert all(isinstance(r, TableResults) for r in seen)

    def test_called_with_none_while_invalid(self, wall):
        seen = []
        wall.on_update(seen.append)
        wall.cell(0, "thickness").value = 0.0
        assert seen[-1] is None

    def test_failing_callback_is_reported_not_raised(self, wall):
        def broken(results):
            raise RuntimeError("plot exploded")

        with pytest.raises(RuntimeError):  # at registration the caller sees it immediately
            wall.on_update(broken)
        wall.cell(0, "thickness").value = 20.0  # later failures are shown, not raised
        assert "Update callback failed: RuntimeError: plot exploded" in text(wall.message)
        assert isinstance(wall.callback_error, RuntimeError)
        assert wall.results is not None  # the table itself is fine


class TestErrors:
    def test_value_error_message_is_shown(self, wall):
        wall.cell(1, "thickness").value = 0.0
        assert wall.results is None
        assert isinstance(wall.error, ValueError)
        assert text(wall.message) == "Thickness must be > 0"
        assert text(wall.cell(0, "R")) == "—" and text(wall.cell(0, "T")) == "—"

    def test_recovers_when_fixed(self, wall):
        wall.cell(1, "thickness").value = 0.0
        wall.cell(1, "thickness").value = 5.0
        assert wall.results is not None and wall.error is None
        assert text(wall.message) == ""

    def test_unexpected_errors_show_their_type(self):
        table = RowTable(columns=[NumberColumn("x"), OutputColumn("y")],
                         compute=lambda inp: {"y": 1 / 0})
        assert text(table.message) == "ZeroDivisionError: division by zero"

    def test_wrong_number_of_outputs(self):
        table = RowTable(columns=[NumberColumn("x"), OutputColumn("y")],
                         compute=lambda inp: {"y": [1.0, 2.0, 3.0]})
        assert text(table.message) == "compute returned 3 values for 'y'; expected 1."

    def test_node_column_needs_one_extra_value(self):
        table = make_cable(compute=lambda inp: {"drop": [0.0, 0.0], "V": [1.0, 2.0]})
        assert "expected 3" in text(table.message)

    def test_message_is_html_escaped(self):
        def compute(inputs):
            raise ValueError("x < 0 & <b>bold</b>")

        table = RowTable(columns=[NumberColumn("x"), OutputColumn("y")], compute=compute)
        assert "&lt;b&gt;" in table.message.value
        assert text(table.message) == "x < 0 & <b>bold</b>"

    def test_leading_output_shows_dash_on_error(self):
        from ipyrowtable import NodeColumn

        def compute(inputs):
            if inputs.column("x")[0] < 0:
                raise ValueError("negative")
            return {"n": [0.0, 1.0]}

        table = RowTable(columns=[NumberColumn("x"), NodeColumn("n", inputs=())], compute=compute)
        table.cell(0, "x").value = -1.0
        assert text(table._leading_outputs["n"]) == "—"
