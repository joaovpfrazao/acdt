# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""API pública e versionada do acdt (``acdt.api``; política em docs/API.md).

Tudo o que está em ``__all__`` é a superfície estável: a assinatura de cada função está fixada em
``api_surface.json`` e um teste falha quando muda sem subir :data:`API_VERSION` (versionamento semântico:
MAIOR = incompatível, MENOR = acréscimo compatível, CORREÇÃO = sem mudança de assinatura). Os módulos internos
(``acdt.core``, ``acdt.domains``, ``acdt.cli``…) podem mudar entre versões do pacote sem aviso.

As funções devolvem estruturas simples (``dict``/``list``/números/texto, serializáveis em JSON) sempre que possível.
Os valores desconhecidos são ``None`` — nunca zero — e "não avaliado" nunca conta como "passa".

Exemplo::

    from acdt import api
    r = api.size("examples/uav_gasoline_150kg.yaml", "out/uav", level="L0")
    print(r["feasible"], r["W0_kg"], r["verification"]["por_estado"])
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from acdt import __version__

from ._deprecation import DEPRECATED, ACDTDeprecationWarning, deprecated

#: Versão semântica da API pública (independente da versão do pacote, :data:`acdt.__version__`).
API_VERSION = "1.7.0"

#: Níveis de fidelidade aceites por :func:`size`/:func:`analyse` (``None`` = o que a missão declara).
LEVELS: dict[str, str] = {"L0": "handbook", "L1": "lowfi"}

PathLike = str | Path

__all__ = [
    "API_VERSION", "LEVELS", "__version__", "ACDTDeprecationWarning", "DEPRECATED", "deprecated", "version_info",
    # projeto
    "load_mission", "analyse", "size", "verify",
    # incerteza, MDO, V&V, calibração
    "uq", "uq_study", "mdo", "mdo_study", "function_model", "vv", "vv_cases", "calibrate", "load_test_data",
    # estado de projeto (design.json)
    "db_load", "db_save", "db_get", "db_diff", "db_validate",
    # relatórios de revisão (SRR/PDR/CDR/MDR/TRR/PRR)
    "report",
    # ruído de rotores/hélices (L0)
    "rotor_noise",
    # gestão térmica (L0/L1), genérica para qualquer tipo de aeronave
    "thermal", "thermal_atmosphere",
    # gelo (L0/L1), genérico para qualquer tipo de aeronave
    "icing", "icing_envelope",
    # fiabilidade e manutenção de frota (L0), genérica para qualquer tipo de aeronave
    "reliability", "availability", "spares_stock",
    # custo de produção em série (L0): CER em função de N, curvas de aprendizagem, ponto de equilíbrio
    "series_cost", "learning_curve",
    # custo do ciclo de vida e pegada ambiental L0
    "life_cycle_cost", "life_cycle_emissions", "present_value",
    # erros
    "errors",
]


def version_info() -> dict[str, str]:
    """Versões: pacote (``acdt``), API pública (``api``) e Python.

    Returns:
        ``{"acdt": "0.2.0", "api": "1.0.0", "python": "3.13.1"}``.
    """
    import platform

    return {"acdt": __version__, "api": API_VERSION, "python": platform.python_version()}


def errors() -> dict[str, type[BaseException]]:
    """Exceções que a API pode levantar por erro de entrada, por nome (para ``except``).

    Returns:
        ``{"InfeasibleError": …, "RequirementError": …, "UnitError": …, "UncertaintySpecError": …,
        "MDOSpecError": …, "CalibrationError": …, "IngestError": …, "VVCaseError": KeyError,
        "ReviewInputError": …}`` (``ReviewInputError`` desde a API 1.1.0).
    """
    from acdt.core.calibration import CalibrationError, IngestError
    from acdt.core.pipeline import InfeasibleError
    from acdt.core.review import ReviewInputError
    from acdt.core.requirements import RequirementError
    from acdt.core.sensitivity.distributions import UncertaintySpecError
    from acdt.core.sysmdo.spec import MDOSpecError
    from acdt.core.units import UnitError

    return {"InfeasibleError": InfeasibleError, "RequirementError": RequirementError, "UnitError": UnitError,
            "UncertaintySpecError": UncertaintySpecError, "MDOSpecError": MDOSpecError,
            "CalibrationError": CalibrationError, "IngestError": IngestError, "VVCaseError": KeyError,
            "ReviewInputError": ReviewInputError}


# ----------------------------------------------------------------------------------------------------- projeto
def _mission_dict(mission: PathLike | Mapping[str, Any]) -> tuple[dict[str, Any], Path | None]:
    import copy

    import yaml

    if isinstance(mission, Mapping):
        return copy.deepcopy(dict(mission)), None
    p = Path(mission)
    if not p.is_file():
        raise FileNotFoundError(f"missão {p} não encontrada")
    return dict(yaml.safe_load(p.read_text(encoding="utf-8")) or {}), p


def load_mission(mission: PathLike | Mapping[str, Any], *, level: str | None = None) -> Any:
    """Lê uma missão (YAML ou ``dict``) para o objeto de especificação do domínio, com unidades normalizadas.

    Args:
        mission: caminho do YAML da missão, ou o mesmo conteúdo já como ``dict`` (os caminhos relativos dentro
            de um ``dict`` resolvem-se a partir da pasta atual).
        level: ``"L0"`` (handbook) ou ``"L1"`` (low-fi XFOIL/AVL) sobrepõe ``assumptions.aero.fidelity``;
            ``None`` mantém o que a missão declara.

    Returns:
        O objeto de especificação do domínio (para ``aircraft``: ``MissionSpec``). Só leitura recomendada: os
        campos internos não fazem parte da API estável.

    Raises:
        FileNotFoundError: o ficheiro não existe.
        ValueError: ``level`` desconhecido, domínio não suportado ou unidade errada na entrada.
    """
    d, src = _mission_dict(mission)
    domain = str(d.get("domain", "aircraft"))
    if domain != "aircraft":
        if src is None or level is not None:
            raise ValueError(f"domínio {domain!r}: só por ficheiro e sem 'level'")
        from acdt.core.pipeline import get_domain

        return get_domain(domain).load_spec(str(src))
    if level is not None:
        if level not in LEVELS:
            raise ValueError(f"level tem de ser um de {sorted(LEVELS)} ou None (recebido {level!r})")
        d.setdefault("assumptions", {}).setdefault("aero", {})["fidelity"] = LEVELS[level]
    from acdt.domains.aircraft.mission import MissionSpec

    return MissionSpec.from_dict(d, src)


def _run(mission: PathLike | Mapping[str, Any], output: PathLike | None, level: str | None,
         no_systems: bool) -> Any:
    from acdt.core.pipeline import run_pipeline

    spec = load_mission(mission, level=level)
    opts: dict[str, Any] = {"no_systems": no_systems}
    if output is not None:
        opts["output"] = Path(output)
    domain = "aircraft" if not hasattr(spec, "domain") else str(getattr(spec, "domain"))
    return run_pipeline(domain, spec, **opts)


def analyse(mission: PathLike | Mapping[str, Any], output: PathLike | None = None, *, level: str | None = None,
            no_systems: bool = False) -> dict[str, Any]:
    """Corre o pipeline completo (dimensionamento + disciplinas + verificação) e devolve o resultado inteiro.

    Args:
        mission: YAML da missão ou ``dict`` (ver :func:`load_mission`).
        output: pasta para relatório, ``result.json``, ``design.json``, matriz de verificação e proveniência;
            ``None`` não escreve ficheiros.
        level: ``"L0"``/``"L1"``/``None`` (ver :func:`load_mission`).
        no_systems: não correr a seleção de sistemas (mais rápido).

    Returns:
        ``{"result": <result.json como dict>, "verification": <matriz acdt.verification/1 ou None>,
        "report": <caminho do relatório ou None>, "output": <pasta ou None>}``.

    Raises:
        InfeasibleError, RequirementError: requisitos inconsistentes ou em falta (ver :func:`errors`).
    """
    from acdt.domains.aircraft.report import to_dict

    st = _run(mission, output, level, no_systems)
    res = st.get("result")
    rep = st.get("report_path")
    return {"result": to_dict(res) if res is not None else None, "verification": st.get("verification"),
            "report": str(rep) if rep else None, "output": str(output) if output is not None else None}


def size(mission: PathLike | Mapping[str, Any], output: PathLike | None = None, *, level: str | None = None,
         no_systems: bool = False) -> dict[str, Any]:
    """Dimensiona a missão e devolve um resumo compacto (o mesmo pipeline de ``acdt size``).

    Args:
        mission: YAML da missão ou ``dict`` (ver :func:`load_mission`).
        output: pasta de saída (``None`` = não escreve ficheiros).
        level: ``"L0"``/``"L1"``/``None`` (ver :func:`load_mission`).
        no_systems: não correr a seleção de sistemas.

    Returns:
        ``{"name", "feasible", "W0_kg", "We_kg", "empty_fraction", "S_m2", "span_m", "iterations",
        "converged", "failed_checks", "issues", "verification": {"requisitos", "por_estado"} | None,
        "report", "output"}``. Grandezas que o pipeline não produziu são ``None``.

    Raises:
        InfeasibleError, RequirementError: requisitos inconsistentes ou em falta.
    """
    import math

    st = _run(mission, output, level, no_systems)
    res, spec = st.get("result"), st.get("spec")

    def num(x: Any) -> float | None:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return None
        return v if math.isfinite(v) else None

    sz = getattr(res, "sizing", None)
    cfg = getattr(res, "config", None)
    wing = getattr(cfg, "wing", None)
    m = st.get("verification")
    cov = (m or {}).get("coverage") or {}
    rep = st.get("report_path")
    return {
        "name": getattr(spec, "name", None),
        "feasible": getattr(res, "feasible", None),
        "W0_kg": num(getattr(sz, "W0", None)),
        "We_kg": num(getattr(sz, "We", None)),
        "empty_fraction": num(getattr(sz, "empty_fraction", None)),
        "S_m2": num(getattr(res, "S", None)),
        "span_m": num(getattr(wing, "span", None)),
        "iterations": getattr(res, "iterations", None),
        "converged": getattr(sz, "converged", None),
        "failed_checks": [c.key for c in getattr(res, "checks", []) if c.ok is False],
        "issues": [{"severity": i.severity, "message": i.message} for i in getattr(res, "issues", [])],
        "verification": ({"requisitos": cov.get("requisitos"), "por_estado": dict(cov.get("por_estado") or {})}
                         if m else None),
        "report": str(rep) if rep else None,
        "output": str(output) if output is not None else None,
    }


def verify(mission: PathLike, output: PathLike) -> dict[str, Any]:
    """Matriz de verificação (``acdt.verification/1``) de uma pasta já corrida, contra os requisitos da missão.

    Args:
        mission: YAML da missão.
        output: pasta de uma corrida anterior (:func:`size`/:func:`analyse` com ``output`` ou ``acdt size -o``).

    Returns:
        A matriz: ``{"schema", "rows": [{"id", "status", "value", …}], "coverage": {"requisitos",
        "por_estado", …}, …}``; estados ``passa``/``falha``/``no_limite``/``nao_avaliado``/``desconhecido``.

    Raises:
        FileNotFoundError: a pasta não tem ``result.json``.
    """
    from acdt.domains.aircraft.verification_run import verify_output

    return verify_output(mission, output)


# ------------------------------------------------------------------------------- incerteza, MDO, V&V, calibração
def uq(mission: PathLike, output: PathLike | None = None, *, uq_file: PathLike | None = None,
       overrides: Mapping[str, Any] | None = None, plots: bool = True) -> dict[str, Any]:
    """Estudo de incerteza e sensibilidade de uma missão (``acdt uq``; docs/INCERTEZA.md).

    Args:
        mission: YAML da missão (com bloco ``uncertainty:``, ou ver ``uq_file``).
        output: pasta para ``uq.json``/``uq.md``/matriz probabilística (``None`` = não escreve).
        uq_file: ficheiro separado com o bloco ``uncertainty:``.
        overrides: sobreposições ao bloco (p.ex. ``{"n": 64, "seed": 1, "sobol": None}``).
        plots: gerar figuras.

    Returns:
        O relatório ``acdt.uq/1`` (nominal, propagação com P5/P50/P95, P(passa) por requisito, Sobol/Morris).
    """
    from acdt.domains.aircraft.uq_run import run_uq

    return run_uq(mission, output, uq_file=uq_file, overrides=overrides, plots=plots)


def function_model(fn: Callable[[Mapping[str, Any]], Mapping[str, float]], params: Mapping[str, Any] | None = None,
                   requirements: Sequence[Mapping[str, Any]] = (), name: str = "função analítica") -> Any:
    """Modelo de sistema a partir de uma função Python, para :func:`uq_study` e :func:`mdo_study`.

    Args:
        fn: ``fn(params) -> {métrica: valor}``; ``params`` = valores fixos ⊕ ponto amostrado/variável.
        params: valores fixos (também dão os nominais das entradas incertas).
        requirements: requisitos rastreáveis ``{"id", "metric", "comparison": "max"|"min"|…, "threshold"
            ou "threshold_param", "tolerance"?, "text"?}``; o valor é a métrica ``metric``.
        name: descrição curta para os relatórios.

    Returns:
        Um modelo com ``run(points)``, ``nominal(path)``, ``requirement_defs()`` e ``with_overrides()``.
    """
    from acdt.core.sysmdo.toy import FunctionModel

    return FunctionModel(fn, dict(params or {}), requirements, name)


def uq_study(uncertainty: Mapping[str, Any], model: Any, output: PathLike | None = None, *,
             plots: bool = False) -> dict[str, Any]:
    """Estudo de incerteza genérico (qualquer modelo; p.ex. :func:`function_model`).

    Args:
        uncertainty: o bloco ``uncertainty:`` (``inputs`` com distribuição e ``source``/``pressuposto``,
            ``n``, ``seed``, ``method``, ``target_probability``, ``sobol``/``morris``…; docs/INCERTEZA.md).
        model: modelo com a interface de :func:`function_model`.
        output: pasta para ``uq.json``/``uq.md`` (``None`` = não escreve).
        plots: gerar figuras.

    Returns:
        O relatório ``acdt.uq/1``.

    Raises:
        UncertaintySpecError: bloco inválido (p.ex. entrada sem origem).
    """
    from acdt.core.sensitivity.study import parse_spec, run_study

    spec = parse_spec(uncertainty, model.nominal)
    return run_study(spec, model, outdir=output, plots=plots)


def mdo(mission: PathLike, output: PathLike | None = None, *, mdo_file: PathLike | None = None,
        overrides: Mapping[str, Any] | None = None, plots: bool = True) -> dict[str, Any]:
    """MDO global de sistema de uma missão (``acdt mdo``; docs/MDO.md).

    Args:
        mission: YAML da missão (com bloco ``mdo:``, ou ver ``mdo_file``).
        output: pasta para ``mdo.json``/``mdo.md``/frente de Pareto (``None`` = não escreve).
        mdo_file: ficheiro separado com o bloco ``mdo:``.
        overrides: ``{"strategy", "options": {...}, "model": {"workers", "fidelity", "skip_stages"}}``.
        plots: gerar figuras.

    Returns:
        ``{"strategy", "evaluations", "pareto", "knee", "chosen", "n_evaluations", "n_feasible", …}``.
    """
    from acdt.domains.aircraft.mdo_system import run_mdo_mission

    return run_mdo_mission(mission, output, mdo_file=mdo_file, overrides=overrides, plots=plots,
                           log=lambda *a, **k: None)


def mdo_study(spec: Mapping[str, Any], model: Any, output: PathLike | None = None, *,
              plots: bool = False) -> dict[str, Any]:
    """MDO genérico (qualquer modelo; p.ex. :func:`function_model`).

    Args:
        spec: o bloco ``mdo:`` (``design_variables`` com ``source``, ``objectives``, ``strategy``
            ``slsqp``/``ga``/``nsga2``/``epsilon``/``doe``, ``options``, ``constraints``…; docs/MDO.md).
        model: modelo com a interface de :func:`function_model`.
        output: pasta para ``mdo.json``/``mdo.md`` (``None`` = não escreve).
        plots: gerar figuras.

    Returns:
        ``{"evaluations", "pareto": [ids], "knee", "best", "chosen", …}``.

    Raises:
        MDOSpecError: bloco inválido.
    """
    from acdt.core.sysmdo.run import run_mdo
    from acdt.core.sysmdo.spec import parse_spec

    return run_mdo(parse_spec(spec, model.nominal), model, outdir=output, plots=plots, log=lambda *a, **k: None)


def vv_cases() -> list[dict[str, Any]]:
    """Casos da biblioteca de V&V (docs/VV.md).

    Returns:
        ``[{"id", "discipline", "kind", "cost", "title"}]`` ordenados por disciplina e id.
    """
    from acdt.core import vv as V

    return [{"id": c.id, "discipline": c.discipline, "kind": c.kind, "cost": c.cost, "title": c.title}
            for c in sorted(V.cases(), key=lambda c: (c.discipline, c.id))]


def vv(cases: Sequence[str] | None = None, disciplines: Sequence[str] | None = None, max_cost: str = "barato",
       output: PathLike | None = None) -> dict[str, Any]:
    """Corre casos de referência publicados (``acdt vv``).

    Args:
        cases: ids a correr (``None`` = todos os do custo pedido).
        disciplines: filtrar por disciplina.
        max_cost: custo máximo (``"barato"``, …; os mais caros ficam ``nao_avaliado``).
        output: pasta para ``vv_report.json``/``.md`` (``None`` = não escreve).

    Returns:
        O relatório ``{"counts": {"passa", "falha", "nao_avaliado", "desconhecido"}, "cases": [...], …}``.

    Raises:
        KeyError: id de caso desconhecido.
    """
    from acdt.core import vv as V

    rep = V.run(ids=cases, disciplines=disciplines, max_cost=max_cost)
    if output is not None:
        V.write(rep, Path(output))
    return rep


def calibrate(study: PathLike, output: PathLike | None = None) -> dict[str, Any]:
    """Calibração de fatores do modelo com dados de ensaio (``acdt calib fit``; docs/CALIBRACAO.md).

    Args:
        study: YAML do estudo (dados, modelo, parâmetros com limites, critérios de aceitação).
        output: pasta para ``calibration_record.json``/``.md`` e resíduos (``None`` = não escreve).

    Returns:
        O registo ``acdt.calib/1`` (parâmetros com incerteza, resíduos, validade, decisão aplicar/rejeitar).

    Raises:
        CalibrationError, IngestError: estudo ou dados inválidos.
    """
    from acdt.core.calibration import run_study

    return run_study(study, output)


def load_test_data(path: PathLike, meta: Mapping[str, Any] | PathLike | None = None) -> Any:
    """Lê dados de ensaio (CSV, Parquet, PX4 ULog) com unidades e metadados (``acdt.testdata/1``).

    Args:
        path: ficheiro de dados.
        meta: metadados (``dict`` ou YAML; por omissão ``<dados>.meta.yaml``).

    Returns:
        O ``Dataset`` (canais em SI com incerteza, metadados, SHA-256 da fonte).

    Raises:
        IngestError: formato, unidade ou metadados inválidos.
    """
    from acdt.core.calibration import load

    return load(path, meta)


# ------------------------------------------------------------------------------------------- estado de projeto
def db_load(path: PathLike, check: bool = True) -> dict[str, Any]:
    """Lê um estado de projeto ``acdt.design/1`` (``design.json`` ou a pasta que o contém).

    Args:
        path: ficheiro ou pasta.
        check: validar o esquema (levanta ``ValueError`` se inválido).

    Returns:
        O estado de projeto como ``dict``.
    """
    from acdt.core import design_db as D

    p = Path(path)
    return D.load(p / D.DEFAULT_FILE if p.is_dir() else p, check=check)


def db_save(db: dict[str, Any], path: PathLike, bump: bool = True) -> Path:
    """Grava um estado de projeto (valida antes; ``bump`` sobe a revisão).

    Returns:
        O caminho escrito.
    """
    from acdt.core import design_db as D

    return D.save(db, path, bump=bump)


def db_get(db: Mapping[str, Any], path: str, unit: str | None = None) -> Any:
    """Valor de uma grandeza do estado de projeto, opcionalmente convertido para ``unit`` (pint).

    Args:
        db: estado de projeto (:func:`db_load`).
        path: caminho exato da grandeza (ver ``acdt db show``).
        unit: unidade de destino (``None`` = a guardada).

    Returns:
        O valor (``None`` se desconhecido — nunca zero).
    """
    from acdt.core import design_db as D

    return D.get_value(db, path, unit)


def db_diff(a: Mapping[str, Any], b: Mapping[str, Any], rtol: float = 1e-6, atol: float = 0.0) -> dict[str, Any]:
    """Diferenças entre dois estados de projeto (valores com tolerância, unidades, nível, proveniência).

    Returns:
        ``{"added", "removed", "changed", "identical", "a", "b", "rtol", "atol"}`` (ver docs/DADOS.md).
    """
    from acdt.core import design_db as D

    return D.diff(a, b, rtol=rtol, atol=atol)


def db_validate(db: Mapping[str, Any]) -> list[str]:
    """Problemas de esquema/unidades de um estado de projeto (lista vazia = válido)."""
    from acdt.core import design_db as D

    return D.validate(db)


# ------------------------------------------------------------------------------------- relatórios de revisão
def report(design: PathLike, level: str, output: PathLike | None = None, *, uq: Sequence[PathLike] = (),
           mdo: Sequence[PathLike] = (), vv: Sequence[PathLike] = (), calib: Sequence[PathLike] = (),
           criteria: PathLike | Mapping[str, Any] | None = None, discover: bool = True,
           pdf: bool = False) -> dict[str, Any]:
    """Relatório de revisão de projeto (SRR, PDR, CDR, MDR, TRR ou PRR; docs/RELATORIOS.md; desde a API 1.1.0).

    Avalia os critérios de entrada e de sucesso de NASA NPR 7123.1D, Apêndice G (Tabelas G-4, G-5, G-6, G-7, G-8
    e G-10) sobre o estado de projeto ``acdt.design/1`` e os registos à volta (matriz de verificação, proveniência,
    UQ, MDO, V&V, calibração), e calcula o veredito: ``pronto``, ``nao_pronto`` ou ``insuficiente`` (falta
    evidência — nunca conta como cumprido). Os critérios que só um painel pode decidir ficam como ``revisao_humana``.

    Args:
        design: ``design.json`` ou a pasta que o contém.
        level: ``"SRR"``, ``"PDR"``, ``"CDR"``, ``"MDR"``, ``"TRR"`` ou ``"PRR"``.
        output: pasta onde escrever ``relatorio_<nível>.json/.md/.html`` (``None`` = só devolve o ``dict``).
        uq: estudos de incerteza extra (``uq.json`` ou pasta), além dos encontrados na pasta do projeto.
        mdo: estudos MDO extra (``mdo.json`` ou pasta).
        vv: relatórios de V&V extra (``vv_report.json`` ou pasta).
        calib: registos de calibração extra (``calibration_record.json`` ou pasta).
        criteria: ficheiro YAML ou ``dict`` com ``waivers``/``tailoring`` (com justificação),
            ``required_level``, ``primary_disciplines``, ``headline``.
        discover: procurar registos na pasta do ``design.json`` (até 3 níveis).
        pdf: também PDF (requer WeasyPrint; ``RuntimeError`` se não estiver instalado).

    Returns:
        O relatório ``acdt.review/1``: ``{"gate", "verdict": {"status", "motivos", "counts"}, "criteria",
        "requirements", "design", "fidelity", "open_items", "uq", "mdo", "vv", "calibration", "traceability",
        "figures", …}`` e ``files`` quando escreve.

    Raises:
        ReviewInputError: ``design.json`` em falta, registo com esquema errado, critérios inválidos.
    """
    from acdt.core import review as R

    return R.report(design, level, output, uq=uq, mdo=mdo, vv=vv, calib=calib, criteria=criteria,
                    discover=discover, pdf=pdf)


def rotor_noise(*, blades: int, diameter_m: float, rpm: float, thrust_N: float, power_W: float, n_rotors: int = 1,
                altitude_m: float = 100.0, speed_m_s: float = 0.0, rho: float = 1.225, c_m_s: float = 340.294,
                blade_area_m2: float | None = None, projected_thickness_m: float | None = None,
                harmonics: int = 10, T_C: float = 15.0, rh_pct: float = 70.0, p_kpa: float = 101.325,
                ground_dB: float = 0.0, ambient_third_octave_dB: Mapping[float, float] | None = None,
                detection_margin_dB: float = 0.0) -> dict[str, Any]:
    """Ruído L0 de rotores/hélices dados explicitamente (desde 1.2.0; docs/RUIDO.md).

    Gutin (tons de carga) + Schlegel-King-Mull (banda larga), absorção ISO 9613-1, ponderação A IEC 61672-1, limiar
    ISO 226. Devolve L_A na vertical, sobrevoo (L_A,max, L_AE), espectro e alcances de deteção auditiva.
    ``thrust_N`` e ``power_W`` são de um rotor; ``speed_m_s`` = 0 é pairar."""
    from acdt.core.acoustics.study import rotor_noise as _rn

    return _rn(blades=blades, diameter_m=diameter_m, rpm=rpm, thrust_N=thrust_N, power_W=power_W, n_rotors=n_rotors,
               altitude_m=altitude_m, speed_m_s=speed_m_s, rho=rho, c_m_s=c_m_s, blade_area_m2=blade_area_m2,
               projected_thickness_m=projected_thickness_m, harmonics=harmonics, T_C=T_C, rh_pct=rh_pct, p_kpa=p_kpa,
               ground_dB=ground_dB, ambient_third_octave_dB=ambient_third_octave_dB,
               detection_margin_dB=detection_margin_dB)


def thermal(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Análise térmica genérica (desde 1.3.0; docs/TERMICA.md): compartimentos, fontes de calor como intervalos,
    condições (atmosferas ISA / MIL-HDBK-310 quente/fria), regime permanente e transitório de capacidade
    concentrada (Incropera et al. 6.ª ed.), ar dinâmico (entrada NACA, NACA RM A8I29) e ventilador, com arrasto,
    massa e potência de arrefecimento. Serve qualquer aeronave (asa fixa, VTOL, jato, híbrido): o chamador dá as
    fontes (W ou [mín, máx]; ``None`` = desconhecido) por condição."""
    from acdt.core.thermal.study import analyse

    return analyse(spec)


def thermal_atmosphere(profile: str, altitude_m: float, *, T_sl_C: float | None = None) -> dict[str, Any]:
    """Ar ambiente de projeto (desde 1.3.0): ``isa``, ``mil310_hot_1pct``, ``mil310_cold_1pct``,
    ``mil310_cold_20pct`` ou ``custom``. Devolve T [°C], p [Pa], ρ [kg/m³] e a fonte."""
    from acdt.core.thermal.air import ambient

    a = ambient(profile, altitude_m, T_sl_C=T_sl_C)
    return {"profile": a.profile, "altitude_m": a.altitude_m, "T_C": a.T_C, "p_Pa": a.p_Pa, "rho_kg_m3": a.rho,
            "source": a.source}


def icing(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Análise de gelo genérica (desde 1.4.0; docs/GELO.md): envelopes do 14 CFR 25 Ap. C (contínuo, intermitente,
    descolagem; Jeck DOT/FAA/AR-00/30), captação na estagnação (Langmuir & Blodgett), fração de congelação e tipo de
    gelo (Messinger), espessura acumulada e potência de proteção (anti-gelo térmico, degelo eletrotérmico), como
    intervalos ``{lo, hi}`` (desconhecido = ``None``). Serve qualquer aeronave: o chamador dá ``conditions``
    (altitude, velocidade, duração) e ``surfaces`` (d = 2 r_le ou corda + t/c, proteção)."""
    from acdt.core.icing.study import analyse

    return analyse(spec)


def icing_envelope(kind: str, T_C: float, mvd_um: float, *, horizontal_extent_nmi: float | None = None,
                   altitude_m: float | None = None) -> dict[str, Any]:
    """LWC de projeto do 14 CFR 25 Ap. C (desde 1.4.0): ``continuous``, ``intermittent`` ou ``takeoff``; com
    ``altitude_m`` diz também se o ponto está dentro do envelope altitude–temperatura (Figs. 2/5)."""
    from acdt.core.icing.envelopes import design_lwc, in_envelope

    r = design_lwc(kind, T_C, mvd_um, horizontal_extent_nmi)
    out: dict[str, Any] = {"kind": kind, "T_C": T_C, "mvd_um": mvd_um, "lwc_g_m3": r.lwc_g_m3,
                           "lwc_standard_g_m3": r.lwc_standard_g_m3, "F": r.F, "horizontal_extent_nmi": r.he_nmi,
                           "note": r.note, "source": r.source}
    if altitude_m is not None:
        out["envelope_status"] = in_envelope(kind, altitude_m, T_C)
    return out


def reliability(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Fiabilidade e manutenção de frota (desde 1.5.0; docs/FIABILIDADE.md): taxas com proveniência (fornecedor com
    fonte e data, base pública ou valor com fonte; sem fonte → desconhecido), RBD (série, paralelo ativo, k-de-n,
    caminhos mínimos), fiabilidade de missão, MTBF básica e MTBCF, M_ct, MTBM, MMH/FH, disponibilidades A_i/A_a/A_o,
    sobressalentes por Poisson, frota (cobertura ou surtidas) e custo de manutenção por FH (MIL-HDBK-338B). Saída em
    intervalos ``{lo, hi}`` (desconhecido = ``None``)."""
    from acdt.core.reliability.study import analyse

    return analyse(spec)


def availability(*, mtbf_h: float | None = None, mttr_h: float | None = None, mtbm_h: float | None = None,
                 m_bar_h: float | None = None, mdt_h: float | None = None,
                 ready_time_h: float = 0.0) -> dict[str, float]:
    """Disponibilidades de MIL-HDBK-338B (desde 1.5.0): intrínseca A_i = MTBF/(MTBF+MTTR) (Eq. 10.18), atingida
    A_a = MTBM/(MTBM+M̄) (Eq. 10.21) e operacional A_o = (MTBM+RT)/(MTBM+RT+MDT) (Eq. 10.22), conforme os pares dados."""
    from acdt.core.reliability import maintenance as mt

    out: dict[str, float] = {}
    if mtbf_h is not None and mttr_h is not None:
        out["inherent"] = mt.inherent_availability(mtbf_h, mttr_h)
    if mtbm_h is not None and m_bar_h is not None:
        out["achieved"] = mt.achieved_availability(mtbm_h, m_bar_h)
    if mtbm_h is not None and mdt_h is not None:
        out["operational"] = mt.operational_availability(mtbm_h, mdt_h, ready_time_h)
    if not out:
        raise ValueError("dê (mtbf_h, mttr_h), (mtbm_h, m_bar_h) e/ou (mtbm_h, mdt_h)")
    return out


def spares_stock(lambda_per_h: float, hours: float, confidence: float) -> dict[str, Any]:
    """Stock de sobressalentes por Poisson (desde 1.5.0; MIL-HDBK-338B Eq. 5.58): menor S com P(X ≤ S) ≥ confiança,
    X ~ Poisson(λ t) (λ e t da procura total, p. ex. frota × utilização × tempo de reabastecimento)."""
    from acdt.core.reliability.spares import poisson_cdf, stock_for

    a = float(lambda_per_h) * float(hours)
    S = stock_for(a, confidence)
    return {"demand_mean": a, "stock": S, "protection": poisson_cdf(S, a),
            "source": "MIL-HDBK-338B Eq. 5.58 (§5.3.8.1)"}


def series_cost(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Custo de produção em série (desde 1.6.0; docs/CUSTO_SERIE.md): CER Eastlake modificado (Gudmundsson 2014
    Cap. 2) ou DAPCA IV (Raymer 2018 Cap. 18) varrida em N com RDT&E / ferramentas / recorrente, custo unitário de
    saída de fábrica e médio, amortizações, ou rota de baixo para cima com curva de aprendizagem (``method:
    learning``); ponto de equilíbrio vs preço (``None`` se não for atingido). Valores em USD (chaves ``*_USD``)."""
    from acdt.domains.aircraft.manufacturing.series import analyse

    return analyse(spec)


def learning_curve(T1: float, slope: float, first: int = 1, last: int = 1, *, theory: str = "crawford",
                   method: str = "exact") -> dict[str, Any]:
    """Curva de aprendizagem (desde 1.6.0): total e média do lote ``first..last``, custo da unidade ``last`` e
    ponto médio do lote. ``theory``: ``crawford`` (unitária, Crawford 1944) ou ``wright`` (média acumulada, Wright
    1936); ``method``: ``exact`` (soma) ou ``approx`` (FAA Pricing Handbook 1998 Eq. 18-9/18-10)."""
    from acdt.domains.aircraft.manufacturing.costing import (learning_b, learning_lot, learning_unit, lot_midpoint,
                                                             wright_unit)

    tot = learning_lot(T1, first, last, slope, theory, method)
    unit = learning_unit(T1, last, slope) if theory == "crawford" else wright_unit(T1, last, slope)
    return {"b": learning_b(slope), "lot_total": tot, "lot_average": tot / (last - first + 1), "unit_last": unit,
            "lot_midpoint": lot_midpoint(first, last, slope),
            "source": "Wright (1936); Crawford (1944); FAA Pricing Handbook (1998) Cap. 18"}


def life_cycle_cost(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Custo do ciclo de vida de um programa (desde 1.7.0; docs/CICLO_VIDA.md): RDT&E + produção + O&S + abate −
    residual (OSD CAPE 2020 §2.1) com calendário (RDT&E, entregas, vida útil), em dólares constantes e em valor
    presente à taxa real declarada (NIST Handbook 135 Eq. 5.1); custo por hora de voo e por missão. Entradas em
    valor ou ``{lo, hi}``; custo desconhecido → majorante ``None``."""
    from acdt.core.lcc.lcc import analyse

    return analyse(spec)


def life_cycle_emissions(spec: Mapping[str, Any]) -> dict[str, Any]:
    """CO₂/CO₂e L0 (desde 1.7.0): combustão (ICAO Anexo 16 Vol. IV: 3,16/3,10 kg CO₂/kg), ciclo de vida do
    combustível (CORSIA LC 89/95 gCO₂e/MJ), eletricidade (intensidade da rede declarada) e fabrico de baterias
    (``ivl_c444_2019`` ou intervalo com fonte); o que faltar fica desconhecido."""
    from acdt.core.lcc.environment import analyse

    return analyse(spec)


def present_value(items: Sequence[Mapping[str, Any]], discount_rate: float) -> float:
    """Valor presente de fluxos (desde 1.7.0; NIST Handbook 135 Eq. 5.1): ``{amount, year}``, ``{amount, annual:
    [t1, t2], escalation}`` ou ``{amount, factor}``."""
    from acdt.core.lcc.lcc import present_value as pv

    return pv(list(items), float(discount_rate))
