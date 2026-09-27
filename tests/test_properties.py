"""Property-based tests (hypothesis).

1. Unit conversions round-trip for any value.
2. A state machine plays random sequences of user actions against a table -- add and remove
   rows with the buttons, type thicknesses, pick materials, set boundary temperatures, flip
   units, and start a new session (a fresh table restoring the saved inputs) -- while
   keeping its own simple model of what the table *should* hold. After every step it checks
   the layout, the stored values, what is displayed, and the physics (against an independent
   nodal-balance solve). Hypothesis shrinks any failure to a minimal sequence.
"""

import shutil
import tempfile
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, precondition, rule

from ipyrowtable.examples.conduction import IMPERIAL, SI
from tests.helpers import CONDUCTIVITY, METRIC, US, make_wall, text

finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


@pytest.mark.parametrize("system", [SI, IMPERIAL, METRIC, US], ids=lambda s: s.name)
@given(value=finite)
def test_unit_round_trip(system, value):
    for quantity in system.units:
        back = system.to_base(quantity, system.to_display(quantity, value))
        assert back == pytest.approx(value, rel=1e-12, abs=1e-9)


@given(value=st.floats(min_value=-1e12, max_value=1e12, allow_nan=False).filter(lambda x: x != 0))
def test_fmt_sig_keeps_four_significant_figures(value):
    from ipyrowtable import fmt_sig

    shown = float(fmt_sig(value).replace(",", ""))
    assert shown == pytest.approx(value, rel=5e-4)


# ------------------------------------------------------------------------ the state machine

MATERIALS = sorted(CONDUCTIVITY)
thickness = st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=500.0))
temperature = st.floats(min_value=-100.0, max_value=1000.0)


def nodal_solve(L, k, T_first, T_last):
    """Independent check: solve the interface energy balances as a linear system."""
    G = np.asarray(k) / np.asarray(L)
    n = len(G)
    T = np.empty(n + 1)
    T[0], T[-1] = T_first, T_last
    if n > 1:
        A = np.zeros((n - 1, n - 1))
        b = np.zeros(n - 1)
        for j in range(n - 1):  # interface j + 1 between layer j and layer j + 1
            A[j, j] = G[j] + G[j + 1]
            if j > 0:
                A[j, j - 1] = -G[j]
            else:
                b[j] += G[j] * T_first
            if j < n - 2:
                A[j, j + 1] = -G[j + 1]
            else:
                b[j] += G[j + 1] * T_last
        T[1:-1] = np.linalg.solve(A, b)
    return T, G[0] * (T[0] - T[1])


class WallMachine(RuleBasedStateMachine):
    @initialize()
    def start(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ipyrowtable-"))
        self.state_file = self.folder / "inputs.json"
        self.table = make_wall(persist="wall", persist_file=self.state_file)
        # the model: what the table should store, in base units
        self.layers = [["steel", 0.010], ["foam", 0.050]]
        self.edges = [100.0, 20.0]

    @property
    def units(self):
        return self.table.units

    def to_base(self, quantity, display_value):
        return self.units.to_base(quantity, display_value)

    # ---- actions, done the way a user does them

    @rule()
    def click_add(self):
        self.table.add_button.click()
        self.layers.append(["steel", self.to_base("length", {"metric": 10.0, "US": 0.5}[
            self.units.name])])

    @precondition(lambda self: len(self.layers) > 1)
    @rule(data=st.data())
    def click_remove(self, data):
        i = data.draw(st.integers(0, len(self.layers) - 1))
        self.table._rows[i]["remove"].click()
        del self.layers[i]

    @rule(data=st.data(), value=thickness)
    def type_thickness(self, data, value):
        i = data.draw(st.integers(0, len(self.layers) - 1))
        self.table.cell(i, "thickness").value = value
        self.layers[i][1] = self.to_base("length", max(value, 0.0))

    @rule(data=st.data(), material=st.sampled_from(MATERIALS))
    def pick_material(self, data, material):
        i = data.draw(st.integers(0, len(self.layers) - 1))
        self.table.cell(i, "material").value = material
        self.layers[i][0] = material

    @rule(end=st.sampled_from(["first", "last"]), value=temperature)
    def type_temperature(self, end, value):
        self.table.edge_widget("T", end).value = value
        self.edges[0 if end == "first" else 1] = self.to_base("temperature", value)

    @rule(name=st.sampled_from(["metric", "US"]))
    def switch_units(self, name):
        self.table.units_toggle.value = name

    @rule()
    def new_session(self):
        """A fresh table with the same key picks up exactly where the last one left off."""
        units = self.table.units.name
        self.table = make_wall(persist="wall", persist_file=self.state_file)
        if self.state_file.exists():
            assert self.table.units.name == units

    def teardown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    # ---- what must always hold

    @invariant()
    def layout_is_consistent(self):
        n = len(self.layers)
        grid = self.table.grid.children
        assert len(grid) == 5 * (2 + n)
        assert grid[-1] is self.table.edge_widget("T", "last")
        assert grid[5 + 4] is self.table.edge_widget("T", "first")
        for i, row in enumerate(self.table._rows):
            assert grid[5 * (2 + i)] is row["remove"]
            assert row["remove"].disabled == (n == 1)

    @invariant()
    def stored_values_match_the_model(self):
        stored = [[r["values"]["material"], r["values"]["thickness"]] for r in self.table._rows]
        assert [m for m, _ in stored] == [m for m, _ in self.layers]
        np.testing.assert_allclose([t for _, t in stored], [t for _, t in self.layers],
                                   rtol=1e-12)
        np.testing.assert_allclose(self.table._edge_values["T"], self.edges, rtol=1e-12)

    @invariant()
    def inputs_display_the_stored_values(self):
        u = self.units
        # A typed value stays exactly as typed; a converted one is rounded to 6 significant
        # figures (tidy), so allow that much.
        for i, (material, L) in enumerate(self.layers):
            assert self.table.cell(i, "material").value == material
            shown = self.table.cell(i, "thickness").value
            assert shown == pytest.approx(u.to_display("length", L), rel=5e-6, abs=1e-12)
        for end, T in zip(["first", "last"], self.edges, strict=True):
            shown = self.table.edge_widget("T", end).value
            assert shown == pytest.approx(u.to_display("temperature", T), rel=5e-6, abs=1e-6)

    @invariant()
    def results_obey_the_physics(self):
        L = np.array([t for _, t in self.layers])
        if np.any(L <= 0):
            assert self.table.results is None
            assert text(self.table.message) == "Thickness must be > 0"
            return
        k = [CONDUCTIVITY[m] for m, _ in self.layers]
        T_expected, q_expected = nodal_solve(L, k, *self.edges)
        r = self.table.results
        scale = max(1.0, abs(self.edges[0]), abs(self.edges[1]))
        np.testing.assert_allclose(r["T"], T_expected, rtol=1e-9, atol=1e-9 * scale)
        # round-off in the independent solve scales with temperature x the largest conductance
        q_tol = 1e-9 * scale * max(CONDUCTIVITY[m] / t for m, t in self.layers)
        assert r["q"] == pytest.approx(q_expected, rel=1e-9, abs=q_tol)
        # the same heat flows through every layer
        np.testing.assert_allclose(-np.diff(r["T"]) / r["R"], r["q"], rtol=1e-6, atol=q_tol)
        # and the table shows those numbers
        shown = [text(self.table.cell(i, "T")) for i in range(len(L) - 1)]
        assert shown == [f"{T:.2f}" for T in r.display("T")[1:-1]]


WallMachine.TestCase.settings = settings(
    max_examples=100,
    stateful_step_count=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
TestWallMachine = WallMachine.TestCase


def test_nodal_solve_matches_a_hand_calculation():
    # 100 mm brick (k = 0.7) + 50 mm foam (k = 0.035), 30 °C / -10 °C:
    # R = 0.142857 + 1.428571 = 1.571429 m²·K/W, q = 40 / 1.571429 = 25.4545 W/m²
    T, q = nodal_solve([0.1, 0.05], [0.7, 0.035], 30.0, -10.0)
    assert q == pytest.approx(25.4545, rel=1e-5)
    assert T[1] == pytest.approx(30.0 - 25.4545 * 0.142857, rel=1e-5)
