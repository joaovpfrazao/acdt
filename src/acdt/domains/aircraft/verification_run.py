"""Liga o pipeline aircraft e ``acdt verify`` à matriz de verificação (acdt.core.verification)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from acdt.core import verification as V

from . import verification_evaluators  # noqa: F401  (regista os avaliadores do domínio)


def traced_requirements(spec: Any) -> list[V.TracedRequirement]:
    return V.requirements_from_mission(spec.requirements, getattr(spec, "verification", None) or {}, "aircraft")


def _scope_fingerprint(spec: Any) -> str | None:
    """Impressão digital da corrida atual: dentro de ``run_scope`` (CLI) usa o âmbito; fora dele (biblioteca)
    reproduz o que ``run_pipeline`` vai escrever (entrada = o ficheiro da missão, executáveis usados)."""
    from acdt.core import provenance as P

    if not P.enabled():
        return None
    try:
        if P.current_scope() is not None:
            return V.provenance_fingerprint(P.collect(probe_versions=False))
        src = getattr(spec, "source", None)
        return V.provenance_fingerprint(P.collect(probe_versions=False, inputs=[src] if src else [],
                                                  tools=P.tools_used_globally()))
    except Exception:  # noqa: BLE001 — sem proveniência a matriz continua, com a impressão digital vazia
        return None


def verify_state(st: Any) -> dict[str, Any]:
    """Etapa final do pipeline: avalia e guarda ``st['verification']``; escreve os ficheiros se houver saída."""
    spec, res = st["spec"], st.get("result")
    if res is None:
        return {}
    reqs = traced_requirements(spec)
    out = st["options"].get("output")
    if out and (Path(out) / "result.json").is_file():
        ctx = V.context_from_output(out, domain="aircraft")
    else:
        from .report import to_dict
        ctx = V.VerificationContext(result=to_dict(res), domain="aircraft")
    ctx.extra["spec"] = spec
    now = _scope_fingerprint(spec)
    if now is not None and ctx.provenance_fingerprint != now:  # provenance.json de uma corrida anterior: ignorar
        ctx.provenance_fingerprint, ctx.provenance_file, ctx.provenance_sha256 = now, None, None
    m = V.verify(reqs, ctx, out if out else None)
    st["verification"] = m
    return m


def verify_output(mission: str | Path, outdir: str | Path) -> dict[str, Any]:
    """``acdt verify``: missão + pasta de saída já corrida → matriz (reescrita na pasta)."""
    from .mission import MissionSpec

    spec = MissionSpec.from_yaml(mission)
    ctx = V.context_from_output(outdir, domain="aircraft")
    ctx.extra["spec"] = spec
    return V.verify(traced_requirements(spec), ctx, outdir)
