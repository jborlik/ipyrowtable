import math

import numpy as np
import pytest

from ipyrowtable import Unit, UnitSystem, fmt_sig
from ipyrowtable.formatting import formatter, tidy

F = UnitSystem("F", {"temperature": Unit("°F", 1.8, 32.0), "length": Unit("in", 1 / 0.0254)})


class TestUnitSystem:
    @pytest.mark.parametrize(("celsius", "fahrenheit"), [(0, 32), (100, 212), (-40, -40)])
    def test_affine_conversion(self, celsius, fahrenheit):
        assert F.to_display("temperature", celsius) == pytest.approx(fahrenheit)
        assert F.to_base("temperature", fahrenheit) == pytest.approx(celsius)

    def test_scale_conversion(self):
        assert F.to_display("length", 0.0254) == pytest.approx(1.0)
        assert F.to_base("length", 12.0) == pytest.approx(0.3048)

    def test_arrays_convert_elementwise(self):
        out = F.to_display("temperature", np.array([0.0, 100.0]))
        assert isinstance(out, np.ndarray)
        np.testing.assert_allclose(out, [32.0, 212.0])

    def test_scalars_come_back_as_python_floats(self):
        assert type(F.to_display("length", 1)) is float
        assert type(F.to_base("length", np.float64(1))) is float

    def test_unlisted_quantity_passes_through(self):
        assert F.to_display("pressure", 5) == 5
        assert F.to_base(None, "text") == "text"
        assert F.label("pressure") == ""
        assert F.label(None) == ""

    def test_labels(self):
        assert F.label("temperature") == "°F"

    def test_default_unit_is_identity(self):
        assert Unit("m").scale == 1.0 and Unit("m").offset == 0.0


class TestFmtSig:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (6050.0, "6,050"),
            (0.8, "0.8000"),
            (79000.0, "79,000"),
            (1.5e-6, "1.500e-06"),
            (0.001234, "0.001234"),
            (-63.99, "-63.99"),
            (123456789.0, "123,456,789"),
            (1.0e9, "1.000e+09"),
            (0.0, "0"),
        ],
    )
    def test_examples(self, value, expected):
        assert fmt_sig(value) == expected

    def test_non_finite(self):
        assert fmt_sig(math.inf) == "inf"
        assert fmt_sig(math.nan) == "nan"

    def test_sig_argument(self):
        assert fmt_sig(3.14159, sig=2) == "3.1"


def test_formatter_variants():
    assert formatter(None)(1234.4) == "1,234"
    assert formatter("{:.1f}")(2.26) == "2.3"
    assert formatter(lambda x: f"<{x}>")(1) == "<1>"


def test_tidy_rounds_to_six_significant_figures():
    assert tidy(0.39370078740157477) == 0.393701
    assert tidy(10.000000000000002) == 10.0
