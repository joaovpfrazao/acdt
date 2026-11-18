# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Finite scalar validation shared by the jet L0 models."""
import math


def bounded(name, value, lower, upper, *, open_lower=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected a finite number")
    if not math.isfinite(value) or value > upper or (value <= lower if open_lower else value < lower):
        raise ValueError(f"{name}: outside {'(' if open_lower else '['}{lower}, {upper}]")
    return value
