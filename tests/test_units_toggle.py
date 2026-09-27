"""Switching unit systems changes what is shown, never the stored values."""

import pytest

from tests.helpers import make_wall, text


def stored(table):
    """Everything the table stores, in base units."""
    return (
        [dict(r["values"]) for r in table._rows],
        {k: list(v) for k, v in table._edge_values.items()},
        dict(table._param_values),
    )


def test_toggle_converts_inputs_headers_and_outputs(wall):
    wall.units_toggle.value = "US"
    assert wall.units.name == "US"
    assert wall.rows == [{"material": "steel", "thickness": 0.393701},
                         {"material": "foam", "thickness": 1.9685}]
    assert (wall.edge_widget("T", "first").value, wall.edge_widget("T", "last").value) == (
        212.0, 68.0)
    assert text(wall.grid.children[2]) == "Thickness (in)"
    assert text(wall.cell(0, "T")) == "211.98"  # 99.99 °C
    assert wall.results.display("q") == pytest.approx(wall.results["q"] * 0.3169983)


def test_units_property_is_the_same_as_the_toggle(wall):
    wall.units = "US"
    assert wall.units_toggle.value == "US"
    wall.units = wall.unit_systems["metric"]  # a UnitSystem works too
    assert wall.units_toggle.value == "metric"


def test_unknown_unit_system(wall):
    with pytest.raises(KeyError):
        wall.units = "cgs"


def test_round_trip_does_not_drift(wall):
    before = stored(wall)
    for _ in range(5):
        wall.units = "US"
        wall.units = "metric"
    assert stored(wall) == before
    assert wall.rows == [{"material": "steel", "thickness": 10.0},
                         {"material": "foam", "thickness": 50.0}]


def test_toggling_does_not_trigger_spurious_edits(wall):
    calls = []
    wall.on_update(calls.append)
    wall.units = "US"
    assert len(calls) == 2  # registration + exactly one recompute for the switch


def test_editing_in_other_units_is_stored_in_base_units(wall):
    wall.units = "US"
    wall.cell(0, "thickness").value = 1.0
    wall.edge_widget("T", "last").value = 32.0
    assert wall._rows[0]["values"]["thickness"] == pytest.approx(0.0254)
    assert wall._edge_values["T"][1] == pytest.approx(0.0)
    wall.units = "metric"
    assert wall.cell(0, "thickness").value == 25.4
    assert wall.edge_widget("T", "last").value == 0.0


def test_new_rows_use_the_current_systems_defaults(wall):
    wall.units = "US"
    wall.add_row()
    assert wall.rows[-1]["thickness"] == 0.5
    wall.add_row({"thickness": 2.0})
    assert wall._rows[-1]["values"]["thickness"] == pytest.approx(0.0508)


def test_choice_selection_survives_switch(wall):
    wall.cell(0, "material").value = "brick"
    wall.units = "US"
    assert wall.cell(0, "material").value == "brick"


def test_starting_in_second_system():
    table = make_wall(units="US", rows=[{"material": "foam", "thickness": 1.0}])
    assert table._rows[0]["values"]["thickness"] == pytest.approx(0.0254)
    assert text(table.grid.children[4]) == "T (°F)"


def test_summary_and_labels_follow_units():
    table = make_wall(summary=lambda r: f"q = {r.display('q'):.1f} {r.units.label('flux')}")
    assert text(table.message).endswith("W/m²")
    table.units = "US"
    assert text(table.message).endswith("Btu/hr·ft²")
