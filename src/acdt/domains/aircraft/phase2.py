"""Fase 2 — estágios pós-dimensionamento do pipeline: estabilidade (AVL + manual) e desempenho.

These stages run on the converged design of the sizing/MDA loop (the V-n diagram and the
wing-box cross-check already run *inside* the loop, see :mod:`sizing`). They only wire the cited
methods of :mod:`stability`, :mod:`structures`, :mod:`performance` and :mod:`aero.avl` together.
"""
from __future__ import annotations

import math

from acdt import G0
from acdt.core.atmosphere import isa
from acdt.core.requirements import Issue

from .sizing import CheckResult, structures_inputs


def stability_stage(res) -> None:
    """Neutral point / CG envelope / tail volumes / control derivatives, AVL cross-check at trimmed cruise."""
    if res.config is None or not math.isfinite(res.S):
        return
    from .aero.avl import avl_available, run_avl_case
    from .stability import stability_analysis
    from .structures import wing_structure
    from .systems_integration import is_uas

    o = res.spec.assumptions["stability"]
    at = isa(res.cruise_altitude)
    CL = res.sizing.W0 * G0 / (0.5 * at.rho * res.cruise_speed**2 * res.S)
    avl = None
    if o.get("use_avl", True) and avl_available():
        try:
            # first pass places the wing; AVL then runs about the resulting aft CG
            st0 = stability_analysis(res, None, o)
            twist = None
            l1 = getattr(res, "structures_l1", None)
            if l1 is not None and l1.elastic is not None and l1.elastic.applied:
                twist = l1.elastic.twist_deg
            avl = _avl_stability_case(run_avl_case, res.config, CL=CL, mach=res.cruise_speed / at.a,
                                      x_ref=_aft_cg_avl_frame(st0, st0.x_wing_apex), wing_twist_deg=twist)
        except Exception as ex:  # pragma: no cover
            res.issues.append(Issue("warning", f"AVL falhou no estágio de estabilidade: {ex}"))
            avl = None
    elif o.get("use_avl", True):
        res.issues.append(Issue("info", "AVL não instalado: estabilidade só por métodos de manual (Raymer Cap. 16)"))
    res.avl = avl
    st = stability_analysis(res, avl, o)
    res.stability = st
    sm_t = o["target_static_margin"]
    res.checks.append(CheckResult("static_margin", st.SM_aft >= sm_t - 1e-3,
                                  f"SM no CG traseiro {100 * st.SM_aft:.1f} % (alvo {100 * sm_t:.0f} %; "
                                  f"dianteiro {100 * st.SM_fwd:.1f} %) — posicionamento da asa por bisseção"))
    trims_ok = all(t["ok"] for t in st.trim.values())
    res.checks.append(CheckResult("trim", trims_ok, "; ".join(f"{k}: δe {t['delta_e_deg']:.1f}°"
                                                             for k, t in st.trim.items())))
    if o.get("dynamics", True):
        _dynamics(res, st, avl, o)
    if avl is not None and res.structures is not None:
        try:
            wr = res.structures.wing_mass_raymer
            res.structures_avl = wing_structure(structures_inputs(
                res.spec, res.sizing.W0, res.config, res.highlift.CLmax_clean, res.structures.vn.CLalpha,
                res.cruise_speed, res.cruise_altitude, wr, is_uas(res.spec),
                res.lowfi.cm0 if res.lowfi else 0.0, avl.strips))
        except Exception as ex:  # pragma: no cover
            res.issues.append(Issue("warning", f"Cargas com distribuição AVL falharam: {ex}"))
    _layout(res)
    _refresh_structures_l1(res)


def _refresh_structures_l1(res) -> None:
    """Re-run the L1 beam at the placed wing station and the solved gear.

    The size loop used 0.35 L because stability had not run. This refresh does not change the polar,
    W0 or the checks. ``elastic.applied`` stays as the size loop left it.
    """
    l1 = getattr(res, "structures_l1", None)
    st = getattr(res, "stability", None)
    if l1 is None or st is None or res.config is None:
        return
    try:
        from .aero.avl import wing_x_ac
        from .structures_l1 import analyse_design
        applied = bool(l1.elastic is not None and l1.elastic.applied)
        k_EI = float(l1.deflections.get("k_EI", 1.0))
        k_GJ = float(l1.deflections.get("k_GJ", 1.0))
        x_wing = st.x_wing_apex + wing_x_ac(res.config.wing)
        fresh = analyse_design(res, k_EI, k_GJ, elastic=True, x_wing=x_wing,
                               gear=getattr(res, "landing_gear", None))
        if fresh.elastic is not None:
            fresh.elastic.applied = applied
        res.structures_l1 = fresh
    except Exception as ex:  # pragma: no cover
        res.issues.append(Issue("warning", f"Actualização da viga L1 após o posicionamento falhou: {ex}"))


def _layout(res) -> None:
    """Operational loading diagram and landing-gear layout. Checks use the wb:/gear: prefixes."""
    from .landing_gear import analyse_landing_gear
    from .weight_balance import analyse_weight_balance

    res.weight_balance = analyse_weight_balance(res)
    wb = res.weight_balance
    if wb is not None and wb.within_limits is not None:
        res.checks.append(CheckResult("wb:envelope", wb.within_limits, wb.message))
    res.landing_gear = analyse_landing_gear(res)
    for key, ok, msg in res.landing_gear.checks:
        res.checks.append(CheckResult(key, ok, msg))
    _assembly(res)


def _assembly(res) -> None:
    """Generic-assembly stage (P1b): ``assumptions.assembly`` = inline spec or ``{file: path}`` (relative to the
    mission yaml). Per-part masses, CG, AVL with bodies, gear and CD0 of the drawn assembly; ``asm:`` checks are
    layout checks (they do not change feasibility). Then ``hq:*`` (except the scissor) and the geometric
    ``gear:*`` are re-evaluated on the assembly (:mod:`.assembly.handling`); ``options.checks_from: fixed_type``
    keeps the fixed-type rows."""
    a = res.spec.assumptions.get("assembly") if isinstance(res.spec.assumptions, dict) else None
    if not a:
        return
    try:
        from .assembly.loop import load_spec
        from .assembly.sizing import assembly_stage
        lp = getattr(res, "assembly_loop", None)
        # in the W0 loop: evaluate the drawing as rescaled to the sized wing; otherwise as drawn
        spec = lp["spec_scaled"] if lp else load_spec(res.spec, a)
        out, cmp = assembly_stage(res, spec)
        res.assembly = {"result": out, "comparison": cmp}
        for key, ok, msg in out.checks:   # None = unassessed stays None (unassessed ≠ fail; 24 nov 2026)
            res.checks.append(CheckResult(key, None if ok is None else bool(ok), msg))
    except Exception as ex:
        res.issues.append(Issue("warning", f"Avaliação da montagem genérica falhou: {ex}"))
        return
    # hq:* (not the scissor) and the geometric gear:* read the drawn assembly, not the fixed type
    from .assembly.handling import apply as assembly_checks
    res.assembly["checks_from_assembly"] = assembly_checks(res, spec, out)


def _avl_stability_case(run_avl_case, config, **kw):
    """Corrida AVL do estágio de estabilidade, repetida uma vez com tempo-limite maior (``lowfi.AVL_TIMEOUTS_S``).

    Um tempo-limite transitório (máquina sobrecarregada) deixava ``avl = None`` e os modos laterais por avaliar, e a
    linha ``hq:spiral`` desaparecia (teste instável de 23 nov 2026, reproduzido por injeção de falha)."""
    from .aero.avl import ToolNotAvailable
    from .aero.lowfi import AVL_TIMEOUTS_S
    last: Exception | None = None
    for tmo in AVL_TIMEOUTS_S:
        try:
            return run_avl_case(config, trim_elevator=True, timeout=tmo, **kw)
        except ToolNotAvailable:
            raise
        except Exception as ex:  # noqa: BLE001 - qualquer falha da corrida externa conta como tentativa falhada
            last = ex
    assert last is not None
    raise last


def _spiral_unassessed_row(res, reason: str) -> None:
    """Sem modos laterais a espiral fica desconhecida, com a linha presente (desconhecido ≠ passa, nunca omitida)."""
    if any(c.key == "hq:spiral" for c in res.checks):
        return
    A = getattr(getattr(res, "spec", None), "assumptions", None)
    geo = (A.get("geometry") if isinstance(A, dict) else None) or {}
    dih = "" if geo.get("dihedral_deg") is not None else (
        "; declare também assumptions.geometry.dihedral_deg (Clβ/espiral precisam de um diedro explícito — "
        "Etkin & Reid 1996 Ch. 6 / MIL-F-8785C Table VIII)")
    res.checks.append(CheckResult("hq:spiral", None, f"espiral unassessed: {reason}{dih}"))


def _dynamics(res, st, avl, o) -> None:
    """Phase 3: scissor plot, dynamic modes and MIL-F-8785C levels (verification checks ``hq:*``)."""
    from .stability import dynamic_modes, handling_qualities, tail_sizing_scissor
    out = {}
    try:
        out["scissor"] = sc = tail_sizing_scissor(res, st, o)
        res.checks.append(CheckResult(
            "hq:scissor", sc["ok"], f"S_h/S atual {sc['Sh_S_current']:.3f} vs mínimo {sc['Sh_S_required']:.3f} "
            f"(estabilidade {sc['Sh_S_stability']:.3f} no CG traseiro, controlo {sc['Sh_S_control']:.3f} a CLmax no "
            f"CG dianteiro; dimensionante: {sc['binding']})"))
    except Exception as ex:  # pragma: no cover
        res.issues.append(Issue("warning", f"Diagrama scissor falhou: {ex}"))
    try:
        out["modes"] = md = dynamic_modes(res, st, avl, o)
        cat, lreq = o.get("hq_category", "B"), int(o.get("hq_required_level", 1))
        out["hq"] = hq = handling_qualities(md, cat)
        out["hq_category"], out["hq_required_level"] = cat, lreq
        from .systems_integration import is_uas
        uav = is_uas(res.spec)
        _A = getattr(getattr(res, "spec", None), "assumptions", None)
        geo = (_A.get("geometry") if isinstance(_A, dict) else None) or {}
        dih_declared = "dihedral_deg" in geo and geo.get("dihedral_deg") is not None
        dih_val = geo.get("dihedral_deg")
        if dih_val is None:
            dih_val = math.degrees(res.config.wing.dihedral) if res.config is not None else 3.0
        for r in hq:
            v = r["valor"]
            vs = f"{v:.3g}" if isinstance(v, float) else str(v)
            ok = r["nível"] <= lreq
            # Spiral uses Clβ which includes geometric dihedral via AVL (Etkin & Reid 1996 Ch. 6;
            # Nelson 1998 Ch. 5). Without an explicit geometry.dihedral_deg the spiral check is
            # unassessed (unknown≠pass), never a silent pass on the 3° TrapezoidalWing default alone.
            if r["key"] == "spiral" and not dih_declared:
                res.checks.append(CheckResult(
                    "hq:spiral", None,
                    f"espiral unassessed: declare assumptions.geometry.dihedral_deg "
                    f"(current TrapezoidalWing default Γ={float(dih_val):g}° is PRESSUPOSTO only; "
                    "Clβ/spiral need an explicit dihedral — Etkin & Reid 1996 Ch. 6 / "
                    "MIL-F-8785C Table VIII)"))
                continue
            extra = ""
            if r["key"] == "spiral":
                extra = (f"; Clβ via AVL with wing dihedral Γ={float(dih_val):g}° "
                         "(Etkin & Reid / Nelson)")
            msg = (f"{r['modo']} = {vs} → Nível {r['nível'] if r['nível'] < 4 else '>3'} "
                   f"(N1: {r['limite N1']}; {r['ref']}, Classe I, Cat. {cat})"
                   + extra + (" — UAV: indicativo" if uav else ""))
            res.checks.append(CheckResult("hq:" + r["key"], ok, msg))
        if md.get("lateral") is None:
            _spiral_unassessed_row(res, "modos laterais não avaliados (" + "; ".join(md.get("notes") or []) + ")")
    except Exception as ex:  # pragma: no cover
        res.issues.append(Issue("warning", f"Modos dinâmicos falharam: {ex}"))
        _spiral_unassessed_row(res, f"modos dinâmicos falharam ({ex})")
    res.dynamics = out


def aeroelastic_stage(res) -> None:
    """Phase 3: divergence / reversal / binary flutter / AEER-45 on the wing box + OAS static coupling."""
    if res.config is None or not math.isfinite(res.S) or res.structures is None:
        return
    o = res.spec.assumptions.get("aeroelasticity", {})
    if not o.get("enabled", True):
        return
    from .aeroelasticity import aeroelastic_analysis
    try:
        ae = aeroelastic_analysis(res, o)
    except Exception as ex:  # pragma: no cover
        res.issues.append(Issue("warning", f"Análise aeroelástica falhou: {ex}"))
        return
    res.aeroelastic = ae
    names = {"divergence": "divergência torsional", "reversal": "inversão de aileron", "flutter": "flutter binário"}
    for k, m in ae.margins.items():
        V = m["V_eas"]
        res.checks.append(CheckResult(
            f"aeroel:{k}", m["ok"], f"{names[k]} V = {V:.1f} m/s EAS vs {m['V_required']:.1f} (= "
            f"{o.get('margin_factor', 1.2):g} V_D); margem {100 * m['margin']:+.0f} %" if math.isfinite(V) else
            f"{names[k]}: não ocorre (V → ∞) vs {m['V_required']:.1f} m/s EAS"))
    a45 = ae.aeer45
    if a45.get("applicable"):
        res.checks.append(CheckResult("aeroel:aeer45", a45["ok"], f"AEER-45 / 23.629(d): F = {a45['F']:.3g} vs "
                                      f"F_max = {a45['F_max']:.3g} (balanceamento do aileron não avaliado)"))


def _aft_cg_avl_frame(st, x_apex):
    """AVL geometry origin is the wing-root leading edge: x_ref = x_cg − x_apex."""
    aft = max(st.cases, key=lambda c: c.xbar_cg)
    return aft.x_cg - x_apex


def performance_stage(res) -> None:
    if res.config is None or not math.isfinite(res.S):
        return
    if res.spec.propulsion_kind == "none":
        # planador: sem missão a motor — polar de velocidades em voo planado (glide.py)
        from .glide import glide_from_result
        gp = glide_from_result(res)
        res.glide = gp
        res.checks.append(CheckResult("perf:planeio", True, f"planeio: (L/D)max {gp.LD_max:.1f} a "
                                      f"{3.6 * gp.V_best_LD:.0f} km/h; afundamento mín. {gp.sink_min:.2f} m/s a "
                                      f"{3.6 * gp.V_min_sink:.0f} km/h (W0, ISA SL, polar parabólica)"))
        return
    from .performance import performance_analysis
    pf = performance_analysis(res, res.spec.assumptions["performance"])
    res.performance = pf
    for c in pf.requirement_compare:
        msg = (f"{c['grandeza']}: {c['obtido']:.4g} {c['unidade']} vs requerido "
               f"{'≥' if c['requisito'] not in ('takeoff_ground_roll', 'landing_distance') else '≤'} "
               f"{c['requerido']:.4g} (missão por segmentos — verificação, não altera a viabilidade do "
               "dimensionamento)")
        res.checks.append(CheckResult(f"perf:{c['requisito']}", c["ok"], msg))
        if not c["ok"]:
            res.issues.append(Issue("warning", "Desempenho por segmentos não cumpre: " + msg))
