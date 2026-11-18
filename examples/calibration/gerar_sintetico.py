# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Gera os dados SINTÉTICOS dos exemplos de calibração (não são ensaios reais; servem para testar a framework).

* ``polar_tunel_sintetico.csv`` — polar parabólica CD = CD0 + CL²/(π·AR·e) com CD0 = 0,0250, e = 0,78, AR = 8,
  ruído normal σ = 0,0004 em CD e σ = 0,005 em CL (semente 20261118);
* ``flexao_estatica_sintetica.csv`` — ensaio estático de flexão: flecha medida = flecha da viga L1 / k_EI com
  k_EI = 0,92, ruído σ = 0,5 mm (semente 20261119).

    python examples/calibration/gerar_sintetico.py
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def main() -> None:
    rng = np.random.default_rng(20261118)
    AR, CD0, e = 8.0, 0.0250, 0.78
    cl = np.linspace(0.05, 1.10, 22)
    cd = CD0 + cl ** 2 / (math.pi * AR * e)
    cl_m = cl + rng.normal(0.0, 0.005, cl.size)
    cd_m = cd + rng.normal(0.0, 0.0004, cl.size)
    lines = ["# DADOS SINTÉTICOS gerados por gerar_sintetico.py (não é um ensaio real)", "CL [1],CD [1],Re [1]"]
    lines += [f"{a:.5f},{b:.6f},{3.0e5:.0f}" for a, b in zip(cl_m, cd_m)]
    (HERE / "polar_tunel_sintetico.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    rng = np.random.default_rng(20261119)
    k_EI = 0.92
    load = np.linspace(200.0, 2000.0, 10)  # N na ponta
    w_beam = 1.0e-5 * load  # m — flecha da viga L1 (linear na carga)
    w = w_beam / k_EI + rng.normal(0.0, 0.0005, load.size)
    lines = ["# DADOS SINTÉTICOS gerados por gerar_sintetico.py (não é um ensaio real)", "load [N],w_beam [m],w [mm]"]
    lines += [f"{a:.1f},{b:.6f},{1000 * c:.3f}" for a, b, c in zip(load, w_beam, w)]
    (HERE / "flexao_estatica_sintetica.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
