"""Number formatting helpers."""

from __future__ import annotations

import numpy as np

__all__ = ["fmt_sig"]


def fmt_sig(x, sig: int = 4) -> str:
    """Format to `sig` significant figures with thousands separators.

    Scientific notation is used only for very large or very small magnitudes.

    >>> fmt_sig(6050.0), fmt_sig(0.8), fmt_sig(1.5e-6)
    ('6,050', '0.8000', '1.500e-06')
    """
    if x == 0 or not np.isfinite(x):
        return f"{x:g}"
    magnitude = int(np.floor(np.log10(abs(x))))
    if -3 <= magnitude < 9:
        return f"{x:,.{max(sig - 1 - magnitude, 0)}f}"
    return f"{x:.{sig - 1}e}"


def formatter(fmt):
    """Turn a format spec (None, a format string like "{:.2f}", or a callable) into a callable."""
    if fmt is None:
        return fmt_sig
    return fmt if callable(fmt) else fmt.format


def tidy(x: float) -> float:
    """Round a converted input value to 6 significant figures for display in an input box."""
    return float(f"{x:.6g}")


def right_aligned(text: str) -> str:
    """HTML for a right-aligned output cell."""
    return f"<div style='text-align:right; padding-right:6px'>{text}</div>"
