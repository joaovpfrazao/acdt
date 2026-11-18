# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Derived maximum on-station time and sizing↔capability closure (L0).

Two genuine numerical problems, nothing else:

1. ``max_feasible``: largest station time T of a FIXED, already sized design for
   which the native forward model completes outbound + T + return + explicit
   operational reserve inside its usable energy/fuel/mass budget. Bracketing by
   doubling, then bisection (Burden & Faires, Numerical Analysis, 9th ed., 2011,
   Sec. 2.1). Monotonicity PRESSUPOSTO: for fixed mass and positive propulsive +
   hotel power, consumption grows with flown time; it is not re-proved per model.
   The returned value is the largest VERIFIED feasible time (conservative).

2. ``capability_closure``: rubber sizing (prop ``sizing.run``, jet ``size_jet``)
   sizes mass for a design station time; a different forward model (prop
   pointmass) can derive a different capability from that mass. Fixed-point
   correction T_d(k+1) = T_d(k) + max(0, T_req - T_max(T_d(k))) + tol — upward only, so
   native takeoff/climb allowances are never stripped to "match" the simulator.
   Residual, tolerance, history and explicit non-convergence states are reported.

No fleet→design loop is invented: with dedicated resources fleet count depends on
the closed sortie, never back on the design.
"""
from acdt.core.energy_storage import number


class Unassessed(ValueError):
    """Forward model could not decide feasibility (missing data/model)."""


def settings(spec):
    s=dict(tolerance_h=.01,search_limit_h=100.,max_iterations=40,closure_tolerance_h=.02,closure_max_iterations=6)
    if spec is None: return s
    if not isinstance(spec,dict) or set(spec)-set(s): raise ValueError("candidate.endurance keys: "+", ".join(sorted(s)))
    s.update(spec)
    for k in ("tolerance_h","search_limit_h","closure_tolerance_h"): number(k,s[k],positive=True)
    for k in ("max_iterations","closure_max_iterations"):
        if isinstance(s[k],bool) or not isinstance(s[k],int) or not 1<=s[k]<=200: raise ValueError(k+" must be integer 1..200")
    if s["closure_tolerance_h"]<s["tolerance_h"]: raise ValueError("closure tolerance cannot be tighter than the endurance search tolerance")
    return s


def max_feasible(feasible, tol_h, limit_h, max_iterations, start_h=.25):
    history=[]
    def f(T):
        ok=feasible(T)
        if ok is None: raise Unassessed("forward feasibility unassessed at station %.6g h"%T)
        history.append(dict(on_station_h=T,feasible=bool(ok)))
        return bool(ok)
    base=dict(value_h=None,lower_bound_h=None,bracket_h=None,iterations=0,tolerance_h=tol_h,search_limit_h=limit_h,history=history,
              method="doubling bracket + bisection (Burden & Faires 2011 Sec. 2.1); largest verified feasible time")
    try:
        if not f(0.):
            return dict(base,status="infeasible_at_zero_station",reason="transit + operational reserve already exceed the usable budget")
        lo,hi=0.,min(max(start_h,tol_h),limit_h)
        while f(hi):
            lo=hi
            if hi>=limit_h:
                return dict(base,status="not_bounded_within_search_limit",lower_bound_h=lo)
            hi=min(2*hi,limit_h)
        it=0
        while hi-lo>tol_h:
            if it>=max_iterations:
                return dict(base,status="max_iterations",lower_bound_h=lo,bracket_h=[lo,hi],iterations=it)
            it+=1; mid=.5*(lo+hi)
            if f(mid): lo=mid
            else: hi=mid
        return dict(base,status="converged",value_h=lo,lower_bound_h=lo,bracket_h=[lo,hi],iterations=it)
    except Unassessed as exc:
        return dict(base,status="unassessed",reason=str(exc))


def capability_closure(evaluate, required_h, tol_h, max_iterations):
    """evaluate(T_design) -> dict(derived=max_feasible result, ok=forward feasibility) or None if sizing failed.

    Converged only when the REQUESTED station time is verified feasible by the
    forward model of the current design; the step overshoots by ``tol_h``.
    """
    history=[]; design=required_h; previous=None; last=None
    for k in range(max_iterations+1):
        ev=evaluate(design); last=ev
        if ev is None:
            return dict(status="sizing_failed",converged=False,history=history,last=None,tolerance_h=tol_h)
        d=ev["derived"]
        if d["status"]!="converged":
            status="capability_infeasible" if d["status"]=="infeasible_at_zero_station" else "capability_unassessed"
            history.append(dict(iteration=k,design_station_h=design,derived_max_on_station_h=None,residual_h=None,search_status=d["status"]))
            return dict(status=status,converged=False,history=history,last=ev,tolerance_h=tol_h)
        r=required_h-d["value_h"]
        covered=ev["ok"](required_h)
        history.append(dict(iteration=k,design_station_h=design,derived_max_on_station_h=d["value_h"],residual_h=r,
                            requested_verified=covered,shortfall_h=max(r,0.),excess_h=max(-r,0.)))
        if covered is None:
            return dict(status="capability_unassessed",converged=False,history=history,last=ev,tolerance_h=tol_h,residual_h=r)
        if covered:
            return dict(status="converged",converged=True,history=history,last=ev,tolerance_h=tol_h,residual_h=r,
                        note="converged = requested station time verified directly by the forward model; residual = requested - derived maximum (bisection lower bound), excess reported, never removed")
        if previous is not None and r>=previous:
            return dict(status="not_contracting",converged=False,history=history,last=ev,tolerance_h=tol_h,residual_h=r)
        previous=r; design+=max(r,0.)+tol_h
    return dict(status="max_iterations",converged=False,history=history,last=last,tolerance_h=tol_h,residual_h=history[-1]["residual_h"])
