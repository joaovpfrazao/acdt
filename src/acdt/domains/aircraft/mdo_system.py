"""``acdt mdo`` no domínio aircraft: o modelo de sistema é o pipeline L0/L1 de ``acdt uq`` (dimensionamento →
estabilidade → aeroelasticidade → desempenho → matriz de verificação), corrido por avaliação sobre uma cópia da
missão com os caminhos das variáveis de projeto substituídos. docs/MDO.md.

Relação com o que já existia: ``acdt optimize`` (``mdo.py``) é o MDF *dentro* do dimensionamento (W/S, P/W, AR com
disciplinas OpenMDAO acopladas e região de confiança); ``acdt mdo`` fica por cima, ao nível do sistema: qualquer
caminho da missão (pressupostos, geometria, requisitos, escolhas discretas) é variável, o pipeline inteiro (que já
fecha o seu próprio MDA de massa) é a análise, e as restrições saem do registo de requisitos.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from acdt.core.sysmdo import MDOSpec, parse_spec, run_mdo
from acdt.core.sysmdo.evaluate import Record

from .uq_run import STAGES, AircraftModel, nominal_of, run_point


def _set_any(d: dict[str, Any], path: str, value: Any) -> None:
    from acdt.core.sensitivity.oat import _set_path

    from .uq_run import set_path

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        set_path(d, path, float(value))
    else:
        _set_path(d, path, copy.deepcopy(value))  # escolha discreta: texto, bloco YAML inteiro, …


class AircraftSystemModel(AircraftModel):
    def with_overrides(self, overrides: Mapping[str, Any]) -> "AircraftSystemModel":
        raw = copy.deepcopy(dict(self.raw))
        for p, v in overrides.items():
            _set_any(raw, p, v)
        return AircraftSystemModel(raw, self.source, self.opts)


def load_mdo(mission: str | Path, mdo_file: str | Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = yaml.safe_load(Path(mission).read_text(encoding="utf-8"))
    if mdo_file:
        m = yaml.safe_load(Path(mdo_file).read_text(encoding="utf-8")) or {}
        m = m.get("mdo", m)
    else:
        m = raw.get("mdo")
    if not m:
        raise ValueError(f"{mission}: sem secção 'mdo' (ou passe --spec ficheiro.yaml)")
    return raw, dict(m)


def run_mdo_mission(mission: str | Path, outdir: str | Path | None = None, *, mdo_file: str | Path | None = None,
                    overrides: Mapping[str, Any] | None = None, plots: bool = True, log: Any = print
                    ) -> dict[str, Any]:
    raw, m = load_mdo(mission, mdo_file)
    ov = dict(overrides or {})
    if ov.get("strategy"):
        m["strategy"] = ov["strategy"]
    if ov.get("options"):
        m["options"] = {**(m.get("options") or {}), **ov["options"]}
    spec: MDOSpec = parse_spec(m, lambda p: nominal_of(raw, p))
    mopts = dict(spec.model)
    mopts.update({k: v for k, v in (ov.get("model") or {}).items() if v is not None})
    if mopts.get("workers") in (None, 0, "auto"):
        mopts["workers"] = max(1, min(8, (os.cpu_count() or 2) - 1))
    mopts["result_paths"] = dict(m.get("result_metrics") or {})
    bad = set(mopts.get("skip_stages") or []) - set(STAGES)
    if bad:
        raise ValueError(f"skip_stages desconhecidas: {sorted(bad)} (etapas: {STAGES})")
    if mopts.get("fidelity") == "handbook":
        spec.pressupostos.append("fidelidade handbook em todas as avaliações (mais barata; muda o modelo)")
    model = AircraftSystemModel(raw, str(Path(mission)), mopts)

    def final_matrix(rec: Record) -> Mapping[str, Any] | None:
        over = dict(rec.extra.get("overrides") or {})
        pt: dict[str, float] = {}
        for k, v in rec.x.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pt[k] = float(v)
            else:
                over[k] = v
        mm = model.with_overrides(over) if over else model
        _s, mat = run_point(mm.raw, mm.source, pt, mopts)
        return mat

    return run_mdo(spec, model, outdir=outdir, plots=plots, log=log, final_matrix=final_matrix)
