"""
Steady-state conduction through a stack of flat plates (a plane composite wall).

A complete ipyrowtable application: a layer table (material and thickness in; conductance and
interface temperature out) with an SI / Imperial toggle and a live temperature-profile plot.

    from ipyrowtable.examples.conduction import layer_stack_app
    app = layer_stack_app(units="SI")        # table and profile plot side by side
    app

    app.stack.results["q"]                    # heat flux, W/m² (base units)
    app.stack.results.display("q")            # the same in the units currently shown
    app.stack.results.display("temperature")  # interface temperatures, top surface first
    app.stack.units = "Imperial"              # same as clicking the toggle

To use your own solver, pass solver=your_function to LayerStack or layer_stack_app; it must
have the same signature and return values as `solve_series_conduction` (SI in and out).
The plot needs matplotlib (pip install ipyrowtable[plot]).
"""

import numpy as np

from .. import (
    ChoiceColumn,
    LiveFigure,
    NodeColumn,
    NumberColumn,
    OutputColumn,
    RowTable,
    Unit,
    UnitSystem,
    fmt_sig,
    side_by_side,
)

__all__ = [
    "MATERIALS",
    "SI",
    "IMPERIAL",
    "UNIT_SYSTEMS",
    "solve_series_conduction",
    "LayerStack",
    "TemperatureProfilePlot",
    "layer_stack_app",
]

# Thermal conductivities near 300 K, in W/(m·K). Edit or extend freely (always SI here).
MATERIALS = {
    "Copper": 401.0,
    "Aluminum": 237.0,
    "Carbon steel": 60.5,
    "Stainless steel (304)": 14.9,
    "Concrete": 1.4,
    "Glass": 1.4,
    "Brick": 0.72,
    "Gypsum board": 0.17,
    "Wood (softwood)": 0.12,
    "Fiberglass insulation": 0.04,
    "Polystyrene foam": 0.03,
}

# ------------------------------------------------------------------------------ units
# Base units (what the solver uses): m, °C, W/m·K, W/m²·K, W/m², m²·K/W.

_W_TO_BTU_PER_HR = 1.0 / 0.29307107  # 1 W = 3.4121 Btu/hr (International Table Btu)
_M_TO_FT = 1.0 / 0.3048
_CONDUCTANCE_TO_IMPERIAL = _W_TO_BTU_PER_HR / _M_TO_FT**2 / 1.8

SI = UnitSystem("SI", {
    "length": Unit("mm", 1000.0),
    "temperature": Unit("°C"),
    "conductivity": Unit("W/m·K"),
    "conductance": Unit("W/m²·K"),
    "heat_flux": Unit("W/m²"),
    "resistance": Unit("m²·K/W"),
})

IMPERIAL = UnitSystem("Imperial", {
    "length": Unit("in", 1.0 / 0.0254),
    "temperature": Unit("°F", 1.8, 32.0),
    "conductivity": Unit("Btu/hr·ft·°F", _W_TO_BTU_PER_HR / _M_TO_FT / 1.8),
    "conductance": Unit("Btu/hr·ft²·°F", _CONDUCTANCE_TO_IMPERIAL),
    "heat_flux": Unit("Btu/hr·ft²", _W_TO_BTU_PER_HR / _M_TO_FT**2),
    "resistance": Unit("hr·ft²·°F/Btu", 1.0 / _CONDUCTANCE_TO_IMPERIAL),
})

UNIT_SYSTEMS = {"SI": SI, "Imperial": IMPERIAL}

# Starting layers, (material, thickness in that system's display units).
DEFAULT_LAYERS = {
    "SI": (("Carbon steel", 10.0), ("Fiberglass insulation", 50.0)),
    "Imperial": (("Carbon steel", 0.375), ("Fiberglass insulation", 2.0)),
}


# ------------------------------------------------------------------------------ solver


def solve_series_conduction(thicknesses, conductivities, T_top, T_bottom):
    """Steady 1-D conduction through flat plates in series, per unit area (all SI).

    Parameters
    ----------
    thicknesses : sequence of float
        Layer thicknesses in m, ordered top to bottom.
    conductivities : sequence of float
        Thermal conductivity of each layer, W/(m·K).
    T_top, T_bottom : float
        Boundary surface temperatures, °C.

    Returns
    -------
    conductances : ndarray, shape (n,)
        Layer conductance k/L, W/(m²·K).
    temperatures : ndarray, shape (n + 1,)
        Interface temperatures in °C, top surface first, bottom surface last.
    q : float
        Heat flux in W/m², positive from top to bottom.
    """
    L = np.asarray(thicknesses, dtype=float)
    k = np.asarray(conductivities, dtype=float)
    conductances = k / L
    resistances = 1.0 / conductances
    q = (T_top - T_bottom) / resistances.sum()
    temperatures = T_top - q * np.concatenate(([0.0], np.cumsum(resistances)))
    return conductances, temperatures, q


# ------------------------------------------------------------------------------ the table


class LayerStack(RowTable):
    """The layer table: material and thickness in; conductance and interface temperature out."""

    def __init__(self, layers=None, T_top=None, T_bottom=None, units="SI", materials=None,
                 solver=solve_series_conduction):
        """
        layers    : iterable of (material_name, thickness), top to bottom, in `units`
                    (mm for SI, inches for Imperial). Defaults to a steel + insulation example.
        T_top     : top boundary temperature in `units` (default 100 °C / 212 °F)
        T_bottom  : bottom boundary temperature in `units` (default 20 °C / 68 °F)
        units     : "SI" or "Imperial" (the toggle can change it later)
        materials : dict {name: k in W/(m·K)}; defaults to MATERIALS
        solver    : function(thicknesses_m, k, T_top_C, T_bottom_C) -> (conductances, temps_C, q)
        """
        self.materials = dict(materials or MATERIALS)
        self.solver = solver
        if layers is None:
            layers = DEFAULT_LAYERS[units]

        super().__init__(
            columns=[
                ChoiceColumn(
                    "material",
                    "Material <span style='font-weight:normal; color:gray'>"
                    "(k in {conductivity})</span>",
                    options=self.materials,
                    label=lambda name, k, u: f"{name}  (k = {u.to_display('conductivity', k):.3g})",
                    width="280px",
                ),
                NumberColumn("thickness", "Thickness ({unit})", quantity="length",
                             default={"SI": 10.0, "Imperial": 0.5}, min=0.0, width="120px"),
                OutputColumn("conductance", "Conductance ({unit})", quantity="conductance",
                             width="200px"),
                NodeColumn("temperature", "Temperature ({unit})", quantity="temperature",
                           first_default=100.0, last_default=20.0, fmt="{:.2f}", width="120px"),
            ],
            compute=self._compute,
            rows=[{"material": m, "thickness": t} for m, t in layers],
            edges={"temperature": (T_top, T_bottom)},
            unit_systems=UNIT_SYSTEMS,
            units=units,
            leading_label="— top surface —",
            item_name="layer",
            summary=self._summary,
            output_quantities={"q": "heat_flux", "R_total": "resistance", "U_total": "conductance"},
        )

    def _compute(self, inputs):
        L = inputs.column("thickness").astype(float)
        if np.any(L <= 0):
            raise ValueError("Every layer needs a thickness greater than zero.")
        k = np.array([self.materials[m] for m in inputs.column("material")])
        T_top, T_bottom = inputs.edges["temperature"]
        conductance, temperature, q = self.solver(L, k, T_top, T_bottom)
        R_total = float(np.sum(1.0 / np.asarray(conductance, dtype=float)))
        return {
            "conductance": conductance,
            "temperature": temperature,
            "q": float(q),
            "R_total": R_total,
            "U_total": 1.0 / R_total,
        }

    @staticmethod
    def _summary(results):
        u = results.units
        return (
            f"Heat flux q = <b>{fmt_sig(results.display('q'))} {u.label('heat_flux')}</b>"
            " (positive top → bottom)"
            f" &nbsp;·&nbsp; total resistance = {fmt_sig(results.display('R_total'))}"
            f" {u.label('resistance')}"
            f" &nbsp;·&nbsp; overall U = {fmt_sig(results.display('U_total'))}"
            f" {u.label('conductance')}"
        )

    # conveniences
    @property
    def T_top(self):
        """The top-temperature input widget."""
        return self.edge_widget("temperature", "first")

    @property
    def T_bottom(self):
        """The bottom-temperature input widget."""
        return self.edge_widget("temperature", "last")

    @property
    def layers(self):
        """Current stack as a list of (material, thickness in display units), top to bottom."""
        return [(row["material"], row["thickness"]) for row in self.rows]


# ------------------------------------------------------------------------------ the profile plot

_PLOT_THEMES = {
    "light": dict(
        surface="#fcfcfb", ink="#0b0b0b", secondary="#52514e", muted="#898781",
        grid="#e1e0d9", axis="#c3c2b7", line="#2a78d6", bands=("#f0efec", "#e6e5e0"),
    ),
    "dark": dict(
        surface="#1a1a19", ink="#ffffff", secondary="#c3c2b7", muted="#898781",
        grid="#2c2c2a", axis="#383835", line="#3987e5", bands=("#242422", "#2e2e2b"),
    ),
}


def _spread(centers, gap, limit):
    """Nudge label positions apart so neighbours are at least `gap` apart, within [gap/2, limit]."""
    y = [max(c, gap / 2) for c in centers]
    for i in range(1, len(y)):
        y[i] = max(y[i], y[i - 1] + gap)
    if y and y[-1] > limit:
        y[-1] = limit
        for i in range(len(y) - 2, -1, -1):
            y[i] = min(y[i], y[i + 1] - gap)
    return y


class TemperatureProfilePlot(LiveFigure):
    """Temperature-vs-depth plot for a LayerStack; redraws itself on every change.

    size  : figure size in inches (width, height)
    theme : "light" or "dark", to match your notebook theme
    dpi   : render resolution; 200 is crisp on hi-DPI screens
    """

    def __init__(self, stack, size=(6.8, 4.4), theme="light", dpi=200):
        self.colors = _PLOT_THEMES[theme]
        super().__init__(stack, size=size, dpi=dpi, facecolor=self.colors["surface"])

    def draw(self, fig, results):
        c = self.colors
        u = results.units
        ax = fig.add_axes([0.13, 0.13, 0.55, 0.70], facecolor=c["surface"])
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(c["axis"])
        ax.tick_params(colors=c["axis"], labelcolor=c["secondary"], labelsize=9, length=3)

        depth = np.concatenate(([0.0], np.cumsum(results.display("thickness"))))
        T = np.asarray(results.display("temperature"))
        total = depth[-1]

        # Layers as alternating neutral bands, separated by a thin surface-colored gap.
        for i in range(len(depth) - 1):
            ax.axhspan(depth[i], depth[i + 1], color=c["bands"][i % 2], lw=0, zorder=0)
        for y in depth[1:-1]:
            ax.axhline(y, color=c["surface"], lw=1.5, zorder=1)
        ax.grid(axis="x", color=c["grid"], lw=0.75)
        ax.set_axisbelow(True)

        # The temperature profile: straight within each layer, kinked at interfaces.
        ax.plot(T, depth, color=c["line"], lw=2, solid_joinstyle="round", solid_capstyle="round",
                marker="o", ms=7, mfc=c["line"], mec=c["surface"], mew=1.5, zorder=3, clip_on=False)

        lo, hi = float(T.min()), float(T.max())
        pad = 0.08 * (hi - lo) if hi > lo else 1.0
        ax.set_xlim(lo - pad, hi + pad)
        ax.set_ylim(total, 0)  # top surface at the top
        ax.set_xlabel(f"Temperature ({u.label('temperature')})", color=c["secondary"], fontsize=9.5)
        ax.set_ylabel(f"Depth from top surface ({u.label('length')})", color=c["secondary"],
                      fontsize=9.5)

        ax.set_title("Temperature profile", loc="left", fontsize=11, color=c["ink"],
                     fontweight="bold", pad=22)
        q = results.display("q")
        direction = "top → bottom" if q >= 0 else "bottom → top"
        ax.text(0, 1.03, f"Heat flux {fmt_sig(abs(q))} {u.label('heat_flux')}, {direction}",
                transform=ax.transAxes, fontsize=9, color=c["secondary"], va="bottom")

        # Material names in the right margin, with leader lines so thin layers stay readable.
        fontsize = 9
        axes_height_pt = fig.get_figheight() * ax.get_position().height * 72
        gap = 1.35 * fontsize * total / axes_height_pt
        centers = (depth[:-1] + depth[1:]) / 2
        for name, y_band, y_label in zip(results["material"], centers,
                                         _spread(centers, gap, total - gap / 2), strict=True):
            ax.annotate(
                name,
                xy=(1.0, y_band), xycoords=("axes fraction", "data"),
                xytext=(1.05, y_label), textcoords=("axes fraction", "data"),
                ha="left", va="center", fontsize=fontsize, color=c["secondary"],
                arrowprops=dict(arrowstyle="-", color=c["muted"], lw=0.75, shrinkA=2, shrinkB=0),
                annotation_clip=False,
            )


# ------------------------------------------------------------------------------ convenience


def layer_stack_app(plot_options=None, **stack_options):
    """A LayerStack and its TemperatureProfilePlot side by side (wrapping on narrow screens).

    stack_options go to LayerStack (layers, T_top, T_bottom, units, materials, solver);
    plot_options go to TemperatureProfilePlot (size, theme, dpi).
    The returned box has .stack and .plot attributes.
    """
    stack = LayerStack(**stack_options)
    plot = TemperatureProfilePlot(stack, **(plot_options or {}))
    app = side_by_side(stack, plot)
    app.stack, app.plot = stack, plot
    return app

