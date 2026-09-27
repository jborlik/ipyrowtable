import ipywidgets as widgets
import pytest

from ipyrowtable import (
    ChoiceColumn,
    Column,
    NodeColumn,
    NumberColumn,
    OutputColumn,
    TextColumn,
    Unit,
    UnitSystem,
)
from tests.helpers import METRIC, US, text

PLAIN = UnitSystem("plain")


class TestHeaders:
    def test_own_unit_placeholder(self):
        col = NumberColumn("t", "Thickness ({unit})", quantity="length")
        assert col.header_text(METRIC) == "Thickness (mm)"
        assert col.header_text(US) == "Thickness (in)"

    def test_other_quantity_placeholder(self):
        col = ChoiceColumn("m", "Material (flux in {flux})", options=["a"])
        assert col.header_text(US) == "Material (flux in Btu/hr·ft²)"

    def test_callable_header(self):
        col = OutputColumn("x", lambda u: f"x [{u.name}]")
        assert col.header_text(METRIC) == "x [metric]"

    def test_header_defaults_to_key(self):
        assert Column("speed").header_text(PLAIN) == "speed"

    def test_width_override(self):
        assert NumberColumn("a").width == "120px"
        assert NumberColumn("a", width="80px").width == "80px"


class TestNumberColumn:
    def test_unbounded_uses_floattext(self):
        w = NumberColumn("a", default=1.0).create_widget(1.0, PLAIN)
        assert type(w) is widgets.FloatText and w.value == 1.0

    def test_bounds_are_converted_to_display_units(self):
        col = NumberColumn("T", quantity="temperature", min=-273.15, max=1000.0)
        w = col.create_widget(25.0, US)
        assert isinstance(w, widgets.BoundedFloatText)
        assert w.value == pytest.approx(77.0)
        assert w.min == pytest.approx(-459.67)
        assert w.max == pytest.approx(1832.0)

    def test_refresh_converts_value_and_bounds(self):
        col = NumberColumn("T", quantity="temperature", min=-273.15)
        w = col.create_widget(25.0, US)
        col.refresh(w, 25.0, METRIC)
        assert (w.value, w.min) == (25.0, -273.15)

    def test_display_values_are_tidied(self):
        col = NumberColumn("L", quantity="length")
        assert col.to_display(0.01, US) == 0.393701

    def test_per_system_defaults(self):
        col = NumberColumn("L", quantity="length", default={"metric": 10.0, "US": 0.5})
        assert col.default_value(METRIC) == pytest.approx(0.010)
        assert col.default_value(US) == pytest.approx(0.0127)


class TestChoiceColumn:
    def test_list_options(self):
        col = ChoiceColumn("c", options=["x", "y"])
        assert col.default == "x"
        w = col.create_widget("y", PLAIN)
        assert list(w.options) == ["x", "y"] and w.value == "y"

    def test_dict_options_with_unit_aware_labels(self):
        speeds = {"slow": 1.0, "fast": 10.0}  # m/s
        units = UnitSystem("imperial", {"speed": Unit("ft/s", 3.28084)})
        col = ChoiceColumn(
            "s", options=speeds,
            label=lambda key, v, u: f"{key} ({u.to_display('speed', v):.3g} {u.label('speed')})",
        )
        w = col.create_widget("fast", units)
        assert w.label == "fast (32.8 ft/s)"
        col.refresh(w, "fast", PLAIN)
        assert (w.label, w.value) == ("fast (10 )", "fast")

    def test_explicit_default(self):
        assert ChoiceColumn("c", options=["x", "y"], default="y").default == "y"

    def test_unknown_value_is_rejected(self):
        with pytest.raises(ValueError, match="not one of"):
            ChoiceColumn("c", options=["x"]).create_widget("z", PLAIN)

    def test_needs_options(self):
        with pytest.raises(ValueError, match="at least one option"):
            ChoiceColumn("c", options=[])


def test_text_column():
    w = TextColumn("name", default="n/a").create_widget("abc", PLAIN)
    assert isinstance(w, widgets.Text) and w.value == "abc" and not w.continuous_update


class TestOutputColumns:
    def test_render_converts_and_formats(self):
        col = OutputColumn("T", quantity="temperature", fmt="{:.1f}")
        assert text(col.render(100.0, US)) == "212.0"

    def test_default_format_is_four_significant_figures(self):
        assert text(OutputColumn("x").render(6050.123, PLAIN)) == "6,050"

    @pytest.mark.parametrize(
        ("inputs", "expected"),
        [(("first", "last"), ("first", "last")), ("first", ("first",)), ((), ())],
    )
    def test_node_inputs(self, inputs, expected):
        assert NodeColumn("T", inputs=inputs).inputs == expected

    def test_node_rejects_unknown_ends(self):
        with pytest.raises(ValueError, match="first"):
            NodeColumn("T", inputs=("top",))

    def test_node_end_defaults_and_bounds(self):
        col = NodeColumn("T", quantity="temperature", first_default={"metric": 100.0, "US": 212.0},
                         last_default=20.0, min=-273.15)
        assert col.ends["first"].default_value(US) == pytest.approx(100.0)
        assert col.ends["last"].default_value(US) == 20.0
        assert col.ends["last"].min == -273.15
