"""Aircraft domain plugin (first domain): conceptual sizing (Phase 1) and systems (1E).

Pipeline: requirements -> sizing/MDA (W0 ↔ constraint diagram ↔ geometry ↔ drag [handbook or
XFOIL/AVL low-fi] ↔ V-n load factor ↔ component weights, wing-box cross-check) -> systems selection
(closed with sizing) -> stability (Phase 2; scissor/modes/HQ Phase 3) -> aeroelasticity (Phase 3)
-> performance (Phase 2) -> report. Optimisation (Phase 3): :mod:`.mdo` (OpenMDAO).
"""
from __future__ import annotations

from acdt.core.pipeline import Domain, DesignState, Stage, register_domain

from . import requirement_types  # noqa: F401  (registers requirement types + validators)
from . import review_profile  # noqa: F401  (perfil de revisão de projeto, acdt report)
from .mission import MissionSpec


def _size(st: DesignState):
    spec = st["spec"]
    use_sys = bool(spec.systems and not st["options"].get("no_systems"))

    def run_fn(sp):  # noqa: ANN001, ANN202
        if use_sys:
            from .systems_integration import run_with_systems
            return run_with_systems(sp)
        from .sizing import run
        return run(sp), None

    th = (spec.assumptions.get("thermal") or {}) if isinstance(spec.assumptions, dict) else {}
    ic = (spec.assumptions.get("icing") or {}) if isinstance(spec.assumptions, dict) else {}
    th_iter = th.get("coupling") == "iterar" and th.get("enabled", True)

    def run_th(sp):  # noqa: ANN001, ANN202
        if th_iter:
            # acoplamento térmico (thermal.py; docs/TERMICA.md): ponto fixo dimensionamento ↔ arrefecimento
            from .thermal import size_with_thermal
            r, s, loop_th = size_with_thermal(sp, run_fn)
            r.thermal_coupling = loop_th
            return r, s
        return run_fn(sp)

    if ic.get("coupling") == "iterar" and ic.get("enabled", True):
        # acoplamento do gelo (icing.py; docs/GELO.md): ponto fixo dimensionamento ↔ proteção contra o gelo
        from .icing import size_with_icing
        res, sysr, loop = size_with_icing(spec, run_th)
        res.icing_coupling = loop
    else:
        res, sysr = run_th(spec)
    st["result"] = res
    if use_sys:
        st["systems"] = sysr
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


def _noise(st: DesignState):
    """Disciplina ruído L0 (noise.py; docs/RUIDO.md): Gutin + Schlegel-King-Mull, ISO 9613-1, ponderação A,
    sobrevoo, deteção auditiva (ISO 226) e, opcional, 14 CFR 36 Ap. G."""
    from .noise import noise_stage
    noise_stage(st["result"])


def _thermal(st: DesignState):
    """Disciplina térmica L0/L1 (thermal.py; docs/TERMICA.md): fontes de calor dos modelos existentes, compartimentos
    em regime permanente e transitório (Incropera), dia quente/frio MIL-HDBK-310, ar dinâmico e acoplamento."""
    from .thermal import thermal_stage
    thermal_stage(st["result"])


def _icing(st: DesignState):
    """Disciplina gelo L0/L1 (icing.py; docs/GELO.md): envelopes 14 CFR 25 Ap. C, captação Langmuir & Blodgett,
    balanço de Messinger, espessura, potência de proteção e acoplamento ao balanço elétrico."""
    from .icing import icing_stage
    icing_stage(st["result"])


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


def _design_db(st: DesignState):
    """Estado de projeto único ``acdt.design/1`` (acdt.core.design_db; docs/DADOS.md): definição, resultados por
    disciplina e nível, matriz. Com pasta de saída escreve design.json (revisão seguinte se já existir)."""
    from acdt.core.requirements import Issue
    try:
        from .design_db_run import write_state
        write_state(st)
    except Exception as ex:  # noqa: BLE001 — o estado de projeto nunca parte o pipeline; fica registado
        st.issues.append(Issue("warning", f"estado de projeto (design.json) não gerado: {type(ex).__name__}: {ex}"))


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
            Stage("noise", _noise, description="ruído de hélice L0 (Gutin, Schlegel-King-Mull), ISO 9613-1, "
                  "ponderação A IEC 61672-1, deteção auditiva ISO 226, 14 CFR 36 Ap. G opcional"),
            Stage("thermal", _thermal, description="gestão térmica L0/L1: compartimentos (Incropera), dia quente/"
                  "frio MIL-HDBK-310, ar dinâmico NACA, arrasto/massa/potência de arrefecimento"),
            Stage("icing", _icing, description="gelo L0/L1: envelopes 14 CFR 25 Ap. C, captação Langmuir & "
                  "Blodgett, Messinger (fração de congelação), espessura, potência de proteção"),
            Stage("report", _report, description="markdown + plots + JSON"),
            Stage("verification", _verification, description="matriz de verificação dos requisitos rastreáveis "
                  "(passa/falha/no_limite/nao_avaliado/desconhecido; docs/REQUISITOS.md)"),
            Stage("design_db", _design_db, description="estado de projeto único acdt.design/1 com unidades, nível e "
                  "proveniência (design.json; docs/DADOS.md)")],
    references=["Raymer 6th ed.", "Roskam I–VIII", "Gudmundsson 2014", "Anderson 1999", "Torenbeek 1982",
                "USAF DATCOM", "Hepperle 2012", "Etkin & Reid 1996", "Nelson 1998", "Megson 2013", "Bruhn 1973",
                "CS-23 / 14 CFR 23", "STANAG 4671", "Drela (XFOIL, AVL)"],
))
