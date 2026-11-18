"""Phase 4: calibration factors L3 (high fidelity) → L1/L2 (low fidelity), with their trace.

Each factor is a plain ratio (or difference) between a high-fidelity result and the *same quantity* of the
low-fidelity model of the *same design*, with the source files of both. They are reported always and applied
only when the user opts in per group (``assumptions.calibration.apply: [aero, flutter, structures]``) — the L1/L2 methods
themselves stay the cited formulas; a calibration multiplies their output (for structures, only k_EI and k_GJ).
Applying a factor outside the design neighbourhood where it was computed is the user's responsibility (the
factors carry the design name and the Phase-4 date).

Groups and where they act:
* ``aero`` (SU2 2-D RANS vs XFOIL, aero/lowfi.py): ``k_clmax`` × section clmax (→ Raymer 12.15 wing CLmax),
  ``d_cm0`` + section cm0 (→ wing torsion, structures.py). ``k_cd_profile`` is the section-cd ratio at
  cl = 0.5 (fully turbulent SU2 RANS-SA / XFOIL, which includes transition). The number and its GCI
  fields are reported and are not applied: the two boundary-layer treatments are not the same cd.
  An inline factor of that name, without ``valid: false``, is still applied when the user opts into aero.
* ``flutter`` (CalculiX modes + DLM p-k vs Phase 3 binary strip estimate, aeroelasticity.py): ``k_flutter`` ×
  strip V_F (→ flutter margin, MDO constraint).
* ``structures`` (CalculiX shell FEM vs Phase 3 box): ``k_EI`` and ``k_GJ`` scale the L1 wing beam
  (EI_used = k_EI · EI_beam, same for GJ) when the user opts into the group. ``k_sigma_cover``,
  ``k_sigma_cap``, ``lambda_buckling`` and the frequency ratios stay reported and are not applied:
  the Phase 3 sizing is a closed-form allowable sizing; a FEM-based resizing is a separate step."""
from __future__ import annotations

import json
import math
from pathlib import Path

GROUPS = ("aero", "flutter", "structures")
APPLICABLE = ("aero", "flutter", "structures")
# Only the stiffness ratios resize the L1 beam. Stress and buckling factors stay diagnostic.
STRUCTURES_APPLIED = ("k_EI", "k_GJ")
# PRESSUPOSTO, not a physical model: a ratio outside this band is not a calibration of the same
# quantity (the Windows PaStiX solve produced k_EI ~ 1e5 and k_sigma_cap ~ 0.008). Differences
# such as d_cm0 may be negative and are not tested against the band.
RATIO_BAND = (0.2, 5.0)
# The ~1.4 ratio sits inside RATIO_BAND. It is still not a calibration: SU2 RANS-SA here is fully
# turbulent and XFOIL includes transition, so the two cds are not the same quantity.
K_CD_PROFILE_NOT_APPLIED = (
    "fully turbulent RANS-SA vs XFOIL with transition: not the same section cd; "
    "ratio reported, not applied"
)


def factor_acceptable(name: str, factor: dict) -> tuple[bool, str]:
    """Whether a stored factor may be applied. ``valid: false`` and ``decision: nao_aplicar`` (H1 records,
    ``acdt calib`` test-data factors) always reject."""
    if factor.get("valid") is False:
        return False, str(factor.get("invalid_reason") or "marked invalid")
    if factor.get("decision") == "nao_aplicar":
        return False, str(factor.get("invalid_reason") or "decision nao_aplicar")
    try:
        value = float(factor["value"])
    except (TypeError, ValueError, KeyError):
        return False, "no numeric value"
    if not math.isfinite(value):
        return False, "non-finite"
    if name.startswith("d_"):
        return True, ""
    if value <= 0.0:
        return False, "non-positive ratio"
    lo, hi = RATIO_BAND
    if not (lo <= value <= hi):
        return False, f"ratio {value:.3g} outside [{lo:g}, {hi:g}]"
    return True, ""


def _stamp(name: str, factor: dict) -> dict:
    ok, why = factor_acceptable(name, factor)
    factor["valid"] = ok
    if not ok:
        factor["invalid_reason"] = why
    return factor


def build(name: str, section: dict | None = None, fem: dict | None = None, flutter: dict | None = None,
          gci: dict | None = None, sources: dict | None = None) -> dict:
    out = {"design": name, "factors": {}, "sources": sources or {},
           "note": "ratios L3/L1-L2 of the same design; applied only if listed in assumptions.calibration.apply"}
    F = out["factors"]
    if section and "k_clmax" in section:
        F["k_clmax"] = _stamp("k_clmax", {"group": "aero", "value": section["k_clmax"], "hifi": section["clmax_rans"],
                        "lowfi": section["clmax_xfoil"], "what": "section clmax at stall Re, SU2 RANS-SA / XFOIL"})
        F["k_cd_profile"] = _stamp("k_cd_profile", {"group": "aero", "value": section["k_cd_profile"],
                             "hifi": section["cd05_rans"], "lowfi": section["cd05_xfoil"],
                             "what": "section cd at cl 0.5, cruise Re, SU2 RANS-SA (fully turbulent) / XFOIL"})
        F["d_cm0"] = _stamp("d_cm0", {"group": "aero", "value": section["d_cm0"], "hifi": section["cm0_rans"],
                      "lowfi": section["cm0_xfoil"], "what": "section cm0 (c/4), RANS − XFOIL"})
        if gci and "cd" in gci:
            F["k_cd_profile"]["gci_fine"] = gci["cd"].get("gci_fine")
            F["k_cd_profile"]["cd_extrapolated"] = gci["cd"].get("f_ext")
            F["k_cd_profile"]["gci_iterative_ok"] = gci["cd"].get("iterative_ok")
            F["k_clmax"]["note"] = "steady RANS-SA near stall: ±10 % typical (NASA TMR); not mesh-converged at stall"
        # After _stamp: a ratio inside RATIO_BAND would otherwise be applied. This comparison is not.
        F["k_cd_profile"]["valid"] = False
        F["k_cd_profile"]["invalid_reason"] = K_CD_PROFILE_NOT_APPLIED
    if fem:
        if "tip_w_fem_m" in fem:
            F["k_EI"] = _stamp("k_EI", {"group": "structures", "value": fem["tip_w_beam_m"] / fem["tip_w_fem_m"],
                         "hifi": fem["tip_w_fem_m"], "lowfi": fem["tip_w_beam_m"],
                         "what": "effective bending stiffness ratio = tip deflection beam(Phase 3 EI) / FEM"})
            F["k_GJ"] = _stamp("k_GJ", {"group": "structures",
                         "value": fem["tip_twist_beam_deg"] / fem["tip_twist_fem_deg"],
                         "hifi": fem["tip_twist_fem_deg"], "lowfi": fem["tip_twist_beam_deg"],
                         "what": "effective torsional stiffness ratio = tip twist beam(Phase 3 Bredt GJ, torque about the mid-box) / FEM"})
        cb = fem.get("cover_bay", {})
        if "sigma_phase3_MPa" in cb and math.isfinite(cb.get("stringer_fem_MPa", math.nan)):
            F["k_sigma_cover"] = _stamp("k_sigma_cover", {"group": "structures",
                                  "value": abs(cb["stringer_fem_MPa"]) / cb["sigma_phase3_MPa"],
                                  "hifi": cb["stringer_fem_MPa"], "lowfi": cb["sigma_phase3_MPa"],
                                  "what": f"upper-cover stringer σ at ultimate, bay {cb['bay']} (y = {cb['y']:.2f} m)"})
        if "cap_fem_MPa" in cb:
            F["k_sigma_cap"] = _stamp("k_sigma_cap", {"group": "structures",
                                "value": abs(cb["cap_fem_MPa"]) / cb["cap_allow_MPa"],
                                "hifi": cb["cap_fem_MPa"], "lowfi": cb["cap_allow_MPa"],
                                "what": "spar-cap abs(σ) at ultimate / allowable (Phase 3 sizing target ≤ 1)"})
        if fem.get("buckling_factors_ultimate"):
            lam = min(fem["buckling_factors_ultimate"])
            F["lambda_buckling"] = _stamp("lambda_buckling", {"group": "structures", "value": lam,
                                    "hifi": lam, "lowfi": 1.0,
                                    "what": "linear buckling eigenvalue at ultimate load (Phase 3 sized to 1.0)"})
        if fem.get("strip_f_bending_Hz") and fem.get("mode_types"):
            fb = next((f for f, t in zip(fem["frequencies_Hz"], fem["mode_types"]) if t == "bending"), None)
            ft = next((f for f, t in zip(fem["frequencies_Hz"], fem["mode_types"]) if t == "torsion"), None)
            if fb:
                F["k_f_bending"] = _stamp("k_f_bending", {"group": "structures", "value": fb / fem["strip_f_bending_Hz"],
                                    "hifi": fb, "lowfi": fem["strip_f_bending_Hz"],
                                    "what": "1st bending frequency FEM / strip"})
            if ft:
                F["k_f_torsion"] = _stamp("k_f_torsion", {"group": "structures",
                                    "value": ft / fem["strip_f_torsion_Hz"], "hifi": ft,
                                    "lowfi": fem["strip_f_torsion_Hz"], "what": "1st torsion frequency FEM / strip"})
    if flutter and flutter.get("margin") and math.isfinite(flutter["margin"].get("V_F_g003", math.nan)):
        vf = flutter["margin"]["V_F_g003"]
        strip = flutter.get("strip_V_F")
        # A non-finite strip speed (no crossing) must not become 0 via IEEE division.
        if isinstance(strip, (int, float)) and math.isfinite(strip) and strip > 0.0:
            F["k_flutter"] = _stamp("k_flutter", {"group": "flutter", "value": vf / strip,
                              "hifi": vf, "lowfi": strip,
                              "what": "flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F"})
        else:
            F["k_flutter"] = {"group": "flutter", "value": None, "hifi": vf, "lowfi": None, "valid": False,
                              "invalid_reason": "strip flutter speed is not finite; ratio not formed",
                              "what": "flutter speed FEM+DLM p-k (g = 0.03, min sym/antisym) / Phase 3 strip V_F"}
    return out


def write(cal: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cal, indent=1, default=float))
    return p


def load(assumptions: dict) -> dict:
    """{name: value} of the factors to *apply*, from ``assumptions.calibration`` (``file`` and/or inline
    ``factors``); empty when ``apply`` is empty."""
    c = (assumptions or {}).get("calibration") or {}
    apply = set(c.get("apply") or [])
    if not apply:
        return {}
    facs = {}
    if c.get("file"):
        d = json.loads(Path(c["file"]).read_text(encoding="utf-8"))
        facs.update({k: v for k, v in d["factors"].items()})
    for k, v in (c.get("factors") or {}).items():
        facs[k] = v if isinstance(v, dict) else {"value": v, "group": _group_of(k)}
    out = {}
    for k, v in facs.items():
        group = v.get("group", _group_of(k))
        if group not in apply or group not in APPLICABLE:
            continue
        if group == "structures" and k not in STRUCTURES_APPLIED:
            continue
        if not factor_acceptable(k, v)[0]:
            continue
        out[k] = float(v["value"])
    return out


def _group_of(k: str) -> str:
    return {"k_clmax": "aero", "k_cd_profile": "aero", "d_cm0": "aero", "k_flutter": "flutter"}.get(k, "structures")


def _cell(x, fmt: str) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"
    return format(v, fmt)


def table_md(cal: dict, applied: dict | None = None) -> list[str]:
    applied = applied or {}
    L = ["| fator | grupo | valor | alta fidelidade | baixa fidelidade | o quê | aplicado |", "|---|---|---|---|---|---|---|"]
    for k, f in cal["factors"].items():
        ok, _why = factor_acceptable(k, f)
        flag = "sim" if ok and k in applied else ("inválido" if not ok else "não")
        L.append(f"| `{k}` | {f['group']} | {_cell(f['value'], '.3f')} | {_cell(f['hifi'], '.4g')} | "
                 f"{_cell(f['lowfi'], '.4g')} | {f['what']} | {flag} |")
    return L
