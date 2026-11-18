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
API_VERSION = "1.0.0"

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
        "MDOSpecError": …, "CalibrationError": …, "IngestError": …, "VVCaseError": KeyError}``.
    """
    from acdt.core.calibration import CalibrationError, IngestError
    from acdt.core.pipeline import InfeasibleError
    from acdt.core.requirements import RequirementError
    from acdt.core.sensitivity.distributions import UncertaintySpecError
    from acdt.core.sysmdo.spec import MDOSpecError
    from acdt.core.units import UnitError

    return {"InfeasibleError": InfeasibleError, "RequirementError": RequirementError, "UnitError": UnitError,
            "UncertaintySpecError": UncertaintySpecError, "MDOSpecError": MDOSpecError,
            "CalibrationError": CalibrationError, "IngestError": IngestError, "VVCaseError": KeyError}


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
