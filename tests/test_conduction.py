"""The plane-wall conduction example: physics, unit conversions and the app.

Physics is checked against things that don't share code with the solver: exact single-layer
results, an independent nodal solve, symmetry, and published conversion constants.
"""

import numpy as np
import pytest

from ipyrowtable.examples.conduction import (
    IMPERIAL,
    MATERIALS,
    SI,
    LayerStack,
    layer_stack_app,
    solve_series_conduction,
)
from tests.helpers import text
from tests.test_properties import nodal_solve


class TestSolver:
    def test_single_layer_is_fouriers_law(self):
        U, T, q = solve_series_conduction([0.2], [0.72], 25.0, 5.0)
        assert q == pytest.approx(0.72 * 20.0 / 0.2)
        np.testing.assert_allclose(U, [3.6])
        np.testing.assert_allclose(T, [25.0, 5.0])

    def test_composite_wall_matches_independent_nodal_solve(self):
        L = [0.012, 0.09, 0.1, 0.003]
        k = [0.17, 0.04, 0.72, 237.0]
        U, T, q = solve_series_conduction(L, k, 21.0, -15.0)
        T_ref, q_ref = nodal_solve(L, k, 21.0, -15.0)
        np.testing.assert_allclose(T, T_ref, rtol=1e-12)
        assert q == pytest.approx(q_ref, rel=1e-12)

    def test_same_flux_through_every_layer(self):
        L, k = [0.01, 0.05, 0.002], [60.5, 0.04, 237.0]
        U, T, q = solve_series_conduction(L, k, 150.0, 25.0)
        np.testing.assert_allclose(U * -np.diff(T), q)

    def test_reversing_the_stack_mirrors_the_profile(self):
        L, k = [0.01, 0.05, 0.002], [60.5, 0.04, 237.0]
        _, T, q = solve_series_conduction(L, k, 150.0, 25.0)
        _, T_rev, q_rev = solve_series_conduction(L[::-1], k[::-1], 25.0, 150.0)
        np.testing.assert_allclose(T_rev, T[::-1])
        assert q_rev == pytest.approx(-q)

    def test_equal_temperatures_mean_no_flux(self):
        _, T, q = solve_series_conduction([0.1, 0.2], [1.0, 2.0], 40.0, 40.0)
        assert q == 0.0
        np.testing.assert_allclose(T, 40.0)


class TestImperialUnits:
    """Conversion constants from NIST SP 811 (International Table Btu)."""

    @pytest.mark.parametrize(
        ("quantity", "one_imperial_in_si"),
        [
            ("conductivity", 1.730735),  # 1 Btu/hr·ft·°F  = 1.730735 W/m·K
            ("conductance", 5.678263),  # 1 Btu/hr·ft²·°F = 5.678263 W/m²·K
            ("heat_flux", 3.154591),  # 1 Btu/hr·ft²    = 3.154591 W/m²
            ("resistance", 0.1761102),  # 1 hr·ft²·°F/Btu = 0.1761102 m²·K/W
            ("length", 0.0254),  # 1 in = 0.0254 m
        ],
    )
    def test_conversion_factors(self, quantity, one_imperial_in_si):
        assert IMPERIAL.to_base(quantity, 1.0) == pytest.approx(one_imperial_in_si, rel=1e-6)

    @pytest.mark.parametrize(("celsius", "fahrenheit"), [(0, 32), (100, 212), (-40, -40)])
    def test_temperature(self, celsius, fahrenheit):
        assert IMPERIAL.to_display("temperature", celsius) == pytest.approx(fahrenheit)

    def test_fiberglass_r_value_per_inch(self):
        # A familiar sanity check: fiberglass batts are roughly R-3 to R-4 per inch.
        stack = LayerStack(layers=[("Fiberglass insulation", 1.0)], units="Imperial")
        assert stack.results.display("R_total") == pytest.approx(3.606, rel=1e-3)

    def test_si_is_the_identity_except_length(self):
        for quantity in ("temperature", "conductivity", "conductance", "heat_flux", "resistance"):
            assert SI.to_display(quantity, 2.5) == 2.5
        assert SI.to_display("length", 0.01) == pytest.approx(10.0)


class TestLayerStack:
    def test_defaults(self):
        stack = LayerStack()
        assert stack.layers == [("Carbon steel", 10.0), ("Fiberglass insulation", 50.0)]
        assert (stack.T_top.value, stack.T_bottom.value) == (100.0, 20.0)
        R = 0.010 / 60.5 + 0.050 / 0.04
        assert stack.results["q"] == pytest.approx(80.0 / R)
        assert text(stack.cell(0, "conductance")) == "6,050"
        assert text(stack.cell(0, "temperature")) == "99.99"

    def test_imperial_defaults(self):
        stack = LayerStack(units="Imperial")
        assert stack.layers == [("Carbon steel", 0.375), ("Fiberglass insulation", 2.0)]
        assert (stack.T_top.value, stack.T_bottom.value) == (212.0, 68.0)
        assert stack.results.inputs.edges["temperature"] == pytest.approx((100.0, 20.0))

    def test_summary_line(self):
        stack = LayerStack()
        assert text(stack.message) == (
            "Heat flux q = 63.99 W/m² (positive top → bottom) · "
            "total resistance = 1.250 m²·K/W · overall U = 0.7999 W/m²·K"
        )
        stack.units = "Imperial"
        assert "20.29 Btu/hr·ft²" in text(stack.message)

    def test_material_labels_follow_units(self):
        stack = LayerStack()
        assert stack.cell(0, "material").label == "Carbon steel  (k = 60.5)"
        stack.units = "Imperial"
        assert stack.cell(0, "material").label == "Carbon steel  (k = 35)"

    def test_zero_thickness_message(self):
        stack = LayerStack()
        stack.cell(0, "thickness").value = 0.0
        assert text(stack.message) == "Every layer needs a thickness greater than zero."

    def test_custom_materials_and_solver(self):
        calls = []

        def solver(L, k, T_top, T_bottom):
            calls.append((list(L), list(k), T_top, T_bottom))
            return solve_series_conduction(L, k, T_top, T_bottom)

        stack = LayerStack(layers=[("unobtainium", 5.0)], materials={"unobtainium": 2.0},
                           solver=solver)
        assert calls[-1] == ([0.005], [2.0], 100.0, 20.0)
        assert stack.results["q"] == pytest.approx(2.0 * 80.0 / 0.005)

    def test_unknown_material(self):
        with pytest.raises(ValueError, match="not one of"):
            LayerStack(layers=[("Kryptonite", 5.0)])

    def test_every_material_is_usable(self):
        stack = LayerStack(layers=[(name, 10.0) for name in MATERIALS])
        assert np.all(np.isfinite(stack.results["temperature"]))


class TestApp:
    def test_app_draws_the_profile(self):
        pytest.importorskip("matplotlib")
        app = layer_stack_app(plot_options={"dpi": 60})
        assert app.children == (app.stack, app.plot)
        assert bytes(app.plot.value).startswith(b"\x89PNG")

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_many_thin_layers_and_reversed_flux(self, theme):
        pytest.importorskip("matplotlib")
        layers = [("Polystyrene foam", 30), ("Copper", 1), ("Aluminum", 1), ("Glass", 3),
                  ("Brick", 100), ("Gypsum board", 12), ("Stainless steel (304)", 1)]
        app = layer_stack_app(layers=layers, T_top=-10, T_bottom=22,
                              plot_options={"theme": theme, "dpi": 60})
        assert app.stack.results["q"] < 0
        assert app.plot.layout.visibility == "visible"

    def test_plot_hides_while_invalid(self):
        pytest.importorskip("matplotlib")
        app = layer_stack_app(plot_options={"dpi": 60})
        app.stack.cell(1, "thickness").value = 0.0
        assert app.plot.layout.visibility == "hidden"
