"""Minimal scipy-based replacement for the `lap` package (used by Ultralytics' ByteTrack).

If `lap` is installed (pip install lap) the original is used and this does nothing.
"""
import sys
import types

import numpy as np
from scipy.optimize import linear_sum_assignment


def lapjv(cost, extend_cost=True, cost_limit=np.inf):
    """Same output as lap.lapjv: (cost, column of each row or -1, row of each column or -1)."""
    cost = np.asarray(cost, float)
    rows, cols = cost.shape
    x = -np.ones(rows, int)
    y = -np.ones(cols, int)
    if cost.size == 0:
        return 0.0, x, y
    r, c = linear_sum_assignment(np.where(cost > cost_limit, cost_limit + 1e6, cost))
    keep = cost[r, c] <= cost_limit
    x[r[keep]] = c[keep]
    y[c[keep]] = r[keep]
    return float(cost[r[keep], c[keep]].sum()), x, y


def install():
    try:
        import lap  # noqa: F401
    except ImportError:
        module = types.ModuleType("lap")
        module.lapjv = lapjv
        module.__version__ = "scipy-shim"
        sys.modules["lap"] = module
