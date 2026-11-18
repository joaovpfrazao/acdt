"""Domain-agnostic OpenMDAO assembly (Phase 3).

A domain supplies *disciplines* as plain Python functions ``f(**inputs) -> dict(outputs)``; this module
wraps each one as an :class:`openmdao.api.ExplicitComponent` (:class:`FunctionComponent`), puts the coupled
ones in a cycle group solved by nonlinear block Gauss–Seidel (NLBGS, Aitken-accelerated) or Newton
(DirectSolver), adds post-processing disciplines after the cycle, and sets up the optimiser
(``ScipyOptimizeDriver``, SLSQP by default). Formulation: MDF (Martins & Lambe, AIAA J. 2013); framework:
Gray et al., "OpenMDAO", Struct. Multidisc. Optim. 59 (2019).

Partial derivatives are finite differences of each discipline (central, relative step) — the disciplines
are the classical handbook/strip-theory methods of the domain, not yet differentiated analytically
(analytic/complex-step partials: Phase 4). Total derivatives of the converged MDA come from the coupled
linear system (LinearBlockGS / DirectSolver), i.e. they are consistent with the MDA, not a black-box FD of
the whole loop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


def openmdao_available() -> bool:
    try:
        import openmdao.api  # noqa: F401
        return True
    except ImportError:
        return False


@dataclass
class Discipline:
    name: str
    fn: Callable[..., dict]
    inputs: dict[str, float]          # name -> default value
    outputs: dict[str, float]         # name -> reference value (scaling) / shape-1 default
    fd_step: float = 1e-6
    fd_form: str = "central"
    reference: str = ""
    cache: dict = field(default_factory=dict)


def _component_class():
    import openmdao.api as om

    class FunctionComponent(om.ExplicitComponent):
        """ExplicitComponent around a domain discipline function (scalar inputs/outputs)."""

        def initialize(self):
            self.options.declare("discipline", recordable=False)

        def setup(self):
            d: Discipline = self.options["discipline"]
            for k, v in d.inputs.items():
                self.add_input(k, val=v)
            for k, ref in d.outputs.items():
                self.add_output(k, val=ref, ref=abs(ref) if ref else 1.0)

        def setup_partials(self):
            d: Discipline = self.options["discipline"]
            self.declare_partials("*", "*", method="fd", step=d.fd_step, form=d.fd_form, step_calc="rel_avg")

        def compute(self, inputs, outputs):
            d: Discipline = self.options["discipline"]
            out = d.fn(**{k: float(inputs[k][0]) for k in d.inputs})
            for k in d.outputs:
                outputs[k] = out[k]
            d.cache["last"] = out

    return FunctionComponent


def build_openmdao_problem(cycle: list[Discipline], post: list[Discipline] | None = None,
                           design_vars: dict[str, dict] | None = None, objective: tuple[str, dict] | None = None,
                           constraints: dict[str, dict] | None = None, solver: str = "nlbgs",
                           maxiter: int = 100, tol: float = 1e-10, driver: str = "SLSQP",
                           opt_maxiter: int = 60, opt_tol: float = 1e-6):
    """Assemble the MDF problem. ``design_vars``: name -> kwargs of ``add_design_var`` (lower, upper, ref);
    ``objective``: (name, kwargs); ``constraints``: name -> kwargs of ``add_constraint``.
    ``solver``: ``nlbgs`` (Aitken NLBGS + LinearBlockGS) or ``newton`` (Newton + DirectSolver)."""
    import openmdao.api as om
    Comp = _component_class()
    prob = om.Problem(reports=False)
    model = prob.model
    if design_vars:
        ivc = om.IndepVarComp()
        for k, kw in design_vars.items():
            ivc.add_output(k, val=kw.get("val", 1.0))
        model.add_subsystem("dvs", ivc, promotes=["*"])
    cyc = model.add_subsystem("mda", om.Group(), promotes=["*"])
    for d in cycle:
        cyc.add_subsystem(d.name, Comp(discipline=d), promotes=["*"])
    if solver == "newton":
        cyc.nonlinear_solver = om.NewtonSolver(solve_subsystems=False, maxiter=maxiter, atol=tol, rtol=tol,
                                               iprint=-1)
        cyc.nonlinear_solver.linesearch = om.ArmijoGoldsteinLS(iprint=-1)
        cyc.linear_solver = om.DirectSolver()
    elif solver == "nlbgs":
        cyc.nonlinear_solver = om.NonlinearBlockGS(maxiter=maxiter, atol=tol, rtol=tol, use_aitken=True, iprint=-1)
        cyc.linear_solver = om.LinearBlockGS(maxiter=maxiter, atol=tol, rtol=tol, iprint=-1)
    else:
        raise ValueError(f"MDA solver '{solver}' unknown (nlbgs | newton)")
    for d in post or []:
        model.add_subsystem(d.name, Comp(discipline=d), promotes=["*"])
    if design_vars:
        for k, kw in design_vars.items():
            model.add_design_var(k, **{a: b for a, b in kw.items() if a != "val"})
    if objective:
        model.add_objective(objective[0], **objective[1])
    for k, kw in (constraints or {}).items():
        model.add_constraint(k, **kw)
    prob.driver = om.ScipyOptimizeDriver(optimizer=driver, maxiter=opt_maxiter, tol=opt_tol, disp=False)
    prob.setup(check=False, mode="fwd")
    for k, kw in (design_vars or {}).items():
        prob.set_val(k, kw.get("val", 1.0))
    return prob
