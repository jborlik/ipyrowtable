"""RowTable structure and behavior, driven the way a user would drive it.

Setting ``widget.value`` is what typing in a box does; ``button.click()`` runs the same
handlers as a mouse click. Assertions check what the table then *shows*.
"""

import ipywidgets as widgets
import numpy as np
import pytest

from ipyrowtable import (
    ChoiceColumn,
    NodeColumn,
    NumberColumn,
    OutputColumn,
    RowTable,
)
from tests.helpers import OHM_PER_M, make_cable, make_wall, text


def shown(table, key):
    """What column `key` shows down the rows: text for outputs, the value for input boxes."""
    cells = [table.cell(i, key) for i in range(len(table))]
    return [text(c) if isinstance(c, widgets.HTML) else c.value for c in cells]


# --------------------------------------------------------------------------- layout


class TestLayout:
    def test_grid_shape_with_node_column(self, wall):
        n_cols = 1 + 4  # remove button + four columns
        assert wall.grid.layout.grid_template_columns.split()[0] == RowTable.REMOVE_WIDTH
        assert len(wall.grid.children) == n_cols * (1 + 1 + 2)  # header, leading row, 2 rows

    def test_headers(self, wall):
        headers = [text(h) for h in wall.grid.children[1:5]]
        assert headers == ["Material", "Thickness (mm)", "R (m²·K/W)", "T (°C)"]

    def test_leading_row_holds_label_and_first_boundary(self, wall):
        leading = wall.grid.children[5:10]
        assert text(leading[1]) == "— top —"
        assert leading[4] is wall.edge_widget("T", "first")

    def test_last_row_shows_editable_last_boundary(self, wall):
        assert wall.grid.children[-1] is wall.edge_widget("T", "last")
        assert wall.cell(1, "T") is wall.edge_widget("T", "last")
        assert wall.cell(0, "T") is not wall.edge_widget("T", "last")

    def test_first_only_boundary(self, cable):
        assert cable.edge_widget("V", "last") is None
        assert text(cable.grid.children[-1]) == shown(cable, "V")[-1]
        assert text(cable.grid.children[-1]) != ""

    def test_output_only_node_column_shows_value_in_leading_row(self):
        table = make_cable(columns=[
            ChoiceColumn("gauge", options=OHM_PER_M),
            NumberColumn("length", default=10.0),
            NodeColumn("V", inputs=()),
        ], compute=lambda inp: {"V": np.arange(len(inp.rows) + 1.0)}, parameters=[],
            rows=[{"gauge": "12 AWG"}, {"gauge": "14 AWG"}])
        leading_node = table.grid.children[4 + 3]  # header row, then the leading row's last cell
        assert text(leading_node) == "0"

    def test_without_node_column_there_is_no_leading_row(self):
        table = RowTable(columns=[NumberColumn("x"), OutputColumn("y")],
                         compute=lambda inp: {"y": inp.column("x")}, rows=[{"x": 1}, {"x": 2}])
        assert len(table.grid.children) == 3 * (1 + 2)

    def test_not_removable_drops_the_button_column(self):
        table = make_wall(removable=False)
        assert len(table.grid.children) == 4 * 4
        assert RowTable.REMOVE_WIDTH not in table.grid.layout.grid_template_columns

    def test_unit_toggle_only_with_several_systems(self, wall, cable):
        assert wall.units_toggle is not None and wall.units_toggle in wall.children
        assert cable.units_toggle is None

    def test_css_classes(self, wall):
        assert "ipyrowtable" in wall._dom_classes
        assert "ipyrowtable-grid" in wall.grid._dom_classes
        assert "ipyrowtable-thickness" in wall.cell(0, "thickness")._dom_classes
        assert "ipyrowtable-T-last" in wall.edge_widget("T", "last")._dom_classes
        assert "ipyrowtable-add" in wall.add_button._dom_classes

    def test_add_button_label(self, wall):
        assert wall.add_button.description == "Add layer"


# --------------------------------------------------------------------------- construction


class TestConstruction:
    def test_default_rows(self):
        table = RowTable(columns=[NumberColumn("x", default=3.0), OutputColumn("y")],
                         compute=lambda inp: {"y": inp.column("x") * 2})
        assert table.rows == [{"x": 3.0}]
        assert text(table.cell(0, "y")) == "6.000"

    def test_initial_edges_in_display_units(self):
        table = make_wall(units="US", edges={"T": (212.0, None)},
                          rows=[{"material": "steel", "thickness": 1.0}])
        assert table.edge_widget("T", "first").value == 212.0
        assert table.edge_widget("T", "last").value == 68.0  # the 20 °C default, in °F
        assert table.results.inputs.edges["T"] == pytest.approx((100.0, 20.0))

    def test_per_system_default_row(self):
        table = make_wall(units="US", rows=[{}])
        assert table.rows == [{"material": "steel", "thickness": 0.5}]

    @pytest.mark.parametrize(
        ("options", "error"),
        [
            (dict(rows=[{"colour": "red"}]), KeyError),
            (dict(edges={"nope": (1, 2)}), KeyError),
            (dict(params={"nope": 1}), KeyError),
            (dict(rows=[]), ValueError),
            (dict(units="imperial"), KeyError),
        ],
    )
    def test_bad_configuration(self, options, error):
        with pytest.raises(error):
            make_wall(**options)

    def test_duplicate_keys_rejected(self):
        with pytest.raises(ValueError, match="Duplicate"):
            RowTable(columns=[NumberColumn("x"), OutputColumn("x")], compute=lambda i: {})

    def test_non_column_rejected(self):
        with pytest.raises(TypeError):
            RowTable(columns=[NumberColumn("x"), "y"], compute=lambda i: {})


# --------------------------------------------------------------------------- adding & removing


class TestAddRemove:
    def test_add_button_appends_default_row(self, wall):
        wall.add_button.click()
        assert len(wall) == 3
        assert wall.rows[-1] == {"material": "steel", "thickness": 10.0}
        assert wall.grid.children[-1] is wall.edge_widget("T", "last")
        assert len(wall.results.inputs.rows) == 3

    def test_add_row_with_values_returns_index(self, wall):
        assert wall.add_row({"material": "brick", "thickness": 100.0}) == 2
        assert wall.rows[2] == {"material": "brick", "thickness": 100.0}

    def test_add_row_rejects_unknown_keys(self, wall):
        with pytest.raises(KeyError):
            wall.add_row({"colour": "red"})

    def test_add_rows_in_one_go(self, wall):
        calls = []
        wall.on_update(calls.append)
        wall.add_rows([{"thickness": 1.0}, {"thickness": 2.0}, {"thickness": 3.0}])
        assert len(wall) == 5 and len(calls) == 2  # once on registration, once for the batch

    def test_remove_button(self, wall):
        wall.cell(0, "thickness").value = 25.0
        wall._rows[0]["remove"].click()
        assert len(wall) == 1
        assert wall.rows == [{"material": "foam", "thickness": 50.0}]
        assert wall.grid.children[-1] is wall.edge_widget("T", "last")

    def test_remove_by_index(self, wall):
        assert wall.remove_row(1) is True
        assert wall.rows == [{"material": "steel", "thickness": 10.0}]

    def test_cannot_remove_below_min_rows(self, wall):
        wall.remove_row(0)
        assert wall._rows[0]["remove"].disabled
        assert wall.remove_row(0) is False
        assert len(wall) == 1

    def test_min_rows_is_configurable(self):
        table = make_wall(min_rows=2)
        assert all(r["remove"].disabled for r in table._rows)
        table.add_row()
        assert not any(r["remove"].disabled for r in table._rows)

    def test_removed_widgets_are_closed(self, wall):
        doomed = wall.cell(0, "thickness")
        wall.remove_row(0)
        assert doomed.comm is None  # closed widgets drop their comm


# --------------------------------------------------------------------------- editing


class TestEditing:
    def test_editing_an_input_recomputes(self, wall):
        before = wall.results["q"]
        wall.cell(1, "thickness").value = 100.0
        assert wall.results["q"] == pytest.approx(before * (0.01 / 50 + 0.05 / 0.035)
                                                  / (0.01 / 50 + 0.1 / 0.035))

    def test_changing_a_choice_recomputes(self, wall):
        wall.cell(1, "material").value = "brick"
        np.testing.assert_allclose(wall.results["R"], [0.01 / 50, 0.05 / 0.7])

    def test_editing_boundaries(self, wall):
        wall.edge_widget("T", "first").value = 50.0
        wall.edge_widget("T", "last").value = 50.0
        assert wall.results["q"] == pytest.approx(0.0)
        assert shown(wall, "T")[0] == "50.00"

    def test_outputs_are_rendered(self, wall):
        # R = L/k = 0.0002 and 1.428571 m²·K/W; q = 80 / 1.428771 = 55.99 W/m²
        assert shown(wall, "R") == ["2.000e-04", "1.429"]
        assert shown(wall, "T")[0] == "99.99"

    def test_text_column(self, cable):
        cable.cell(0, "name").value = "panel to box"
        assert cable.rows[0]["name"] == "panel to box"

    def test_parameter(self, cable):
        drop_15 = cable.results["drop"].copy()
        cable.param_widget("current").value = 30.0
        np.testing.assert_allclose(cable.results["drop"], 2 * drop_15)
        assert cable.params == {"current": 30.0}

    def test_parameter_initial_value(self):
        assert make_cable(params={"current": 5.0}).results.inputs.params == {"current": 5.0}

    def test_parameter_label(self, cable):
        assert "Current (A)" in text(cable._param_labels["current"])

    def test_choice_parameter(self):
        fluids = {"water": 1000.0, "oil": 850.0}
        table = RowTable(
            columns=[NumberColumn("h", default=1.0), OutputColumn("p")],
            compute=lambda inp: {"p": fluids[inp.params["fluid"]] * 9.81 * inp.column("h")},
            parameters=[ChoiceColumn("fluid", "Fluid", options=fluids)],
        )
        assert table.results["p"][0] == pytest.approx(9810.0)
        table.param_widget("fluid").value = "oil"
        assert table.results["p"][0] == pytest.approx(850 * 9.81)

    def test_recompute_picks_up_external_changes(self):
        factor = {"k": 2.0}
        table = RowTable(columns=[NumberColumn("x", default=1.0), OutputColumn("y")],
                         compute=lambda inp: {"y": inp.column("x") * factor["k"]})
        factor["k"] = 3.0
        table.recompute()
        assert table.results["y"][0] == 3.0

    def test_widget_types(self, wall):
        assert isinstance(wall.cell(0, "material"), widgets.Dropdown)
        assert isinstance(wall.cell(0, "thickness"), widgets.BoundedFloatText)
        assert isinstance(wall.cell(0, "R"), widgets.HTML)
