"""Aircraft domain plugin (first domain): conceptual sizing (Phase 1) and systems (1E).

Pipeline: requirements -> sizing/MDA (W0 ↔ constraint diagram ↔ geometry ↔ drag [handbook or
XFOIL/AVL low-fi] ↔ V-n load factor ↔ component weights, wing-box cross-check) -> systems selection
(closed with sizing) -> stability (Phase 2; scissor/modes/HQ Phase 3) -> aeroelasticity (Phase 3)
-> performance (Phase 2) -> report. Optimisation (Phase 3): :mod:`.mdo` (OpenMDAO).
"""
from __future__ import annotations

from acdt.core.pipeline import Domain, DesignState, Stage, register_domain

from . import requirement_types  # noqa: F401  (registers requirement types + validators)
from .mission import MissionSpec


def _size(st: DesignState):
    spec = st["spec"]
    if spec.systems and not st["options"].get("no_systems"):
        from .systems_integration import run_with_systems
        st["result"], st["systems"] = run_with_systems(spec)
    else:
        from .sizing import run
        st["result"] = run(spec)
    st.issues += st["result"].issues


def _stability(st: DesignState):
    from .phase2 import stability_stage
    stability_stage(st["result"])


def _performance(st: DesignState):
    from .phase2 import performance_stage
    performance_stage(st["result"])


def _aeroelastic(st: DesignState):
    from .phase2 import aeroelastic_stage
    aeroelastic_stage(st["result"])


def _report(st: DesignState):
    out = st["options"].get("output")
    if out:
        from .report import write_report
        st["report_path"] = write_report(st["result"], out)


def _verification(st: DesignState):
    """Matriz de verificação (acdt.core.verification): cada requisito da missão e de ``verification.requirements``
    avaliado contra os resultados. Com pasta de saída escreve verification_matrix.{json,md,csv}."""
    from acdt.core.requirements import Issue
    try:
        from .verification_run import verify_state
        verify_state(st)
    except Exception as ex:  # noqa: BLE001 — a matriz nunca parte o pipeline; fica registado
        st.issues.append(Issue("warning", f"matriz de verificação não gerada: {type(ex).__name__}: {ex}"))


DOMAIN = register_domain(Domain(
    name="aircraft",
    description="Fixed-wing aircraft and UAS",
    load_spec=MissionSpec.from_yaml,
    stages=[Stage("sizing+systems", _size, description="Raymer/Roskam/Gudmundsson sizing, MDA, systems"),
            Stage("stability", _stability, description="neutral point, CG envelope, tail volumes, control "
                  "derivatives (Raymer Ch. 16, Etkin, Nelson) + AVL"),
            Stage("aeroelasticity", _aeroelastic, description="torsional divergence, aileron reversal, binary "
                  "flutter, AEER-45 (Wright & Cooper, Bisplinghoff) + OpenAeroStruct static coupling"),
            Stage("performance", _performance, description="segment mission, payload-range, field lengths, "
                  "ceilings (Raymer Ch. 17, Anderson)"),
            Stage("report", _report, description="markdown + plots + JSON"),
            Stage("verification", _verification, description="matriz de verificação dos requisitos rastreáveis "
                  "(passa/falha/no_limite/nao_avaliado/desconhecido; docs/REQUISITOS.md)")],
    references=["Raymer 6th ed.", "Roskam I–VIII", "Gudmundsson 2014", "Anderson 1999", "Torenbeek 1982",
                "USAF DATCOM", "Hepperle 2012", "Etkin & Reid 1996", "Nelson 1998", "Megson 2013", "Bruhn 1973",
                "CS-23 / 14 CFR 23", "STANAG 4671", "Drela (XFOIL, AVL)"],
))
