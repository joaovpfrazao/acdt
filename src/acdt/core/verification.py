"""Requisitos rastreáveis e matriz de verificação (domínio-agnóstico).

Cada requisito tem um ID estável, texto, origem (missão, regulamento, norma, SORA, utilizador ou derivado), pais,
grandeza + unidade + comparação + limiar (e objetivo opcional), tolerância declarada, método de verificação, nível
de fidelidade exigido e o **avaliador** que o verifica. Depois de uma corrida, :func:`evaluate` avalia cada
requisito contra os resultados e devolve um estado em :data:`STATUSES`:

* ``passa`` — o avaliador correu, há valor e cumpre fora da banda de tolerância;
* ``falha`` — o avaliador correu, há valor e não cumpre fora da banda;
* ``no_limite`` — o valor está dentro da tolerância declarada em torno do limiar (nem passa nem falha; a mesma
  regra de ``side_load_band``, 14 CFR 23.485);
* ``nao_avaliado`` — não há avaliador, o avaliador não está registado, ou a etapa que o alimenta não correu nesta
  corrida (ou correu com fidelidade abaixo da exigida);
* ``desconhecido`` — o avaliador correu mas não deu valor/veredicto (dados em falta, NaN, «não avaliado» interno).

Nunca ``passa`` sem o avaliador ter corrido e devolvido um valor ou veredicto (desconhecido ≠ zero; não avaliado
≠ passa).

Métodos de verificação (vocabulário V&V): ``analise``, ``simulacao``, ``ensaio``, ``inspecao``, ``demonstracao``,
``revisao``. Referências: NASA/SP-2016-6105 Rev2 (NASA Systems Engineering Handbook — test, analysis, inspection,
demonstration) e ECSS-E-ST-10-02C (Verification — test, analysis, review-of-design, inspection). ``simulacao`` é
análise por modelo dinâmico (6-DOF, missão por segmentos), separada para leitura.

Os avaliadores são registados pelos domínios (:func:`register_evaluator`); o núcleo só tem o genérico
``resultado:<caminho.no.json>``. O registo de proveniência (``acdt.provenance/1``) liga-se à matriz pela
impressão digital :func:`provenance_fingerprint` (commit, árvore suja, versões, SO, SHA-256 dos executáveis,
entradas e sementes — sem datas nem manifesto de saídas, por isso é a mesma antes e depois de o registo ser
escrito) e, quando já existe no disco, pelo SHA-256 do ``provenance.json``.
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "acdt.verification/1"
STATUSES = ("passa", "falha", "no_limite", "nao_avaliado", "desconhecido")
# pior primeiro: usado para agregar os filhos num pai sem avaliador próprio
_SEVERITY = {"falha": 0, "desconhecido": 1, "nao_avaliado": 2, "no_limite": 3, "passa": 4}
METHODS = ("analise", "simulacao", "ensaio", "inspecao", "demonstracao", "revisao")
_METHOD_ALIASES = {"analysis": "analise", "análise": "analise", "simulation": "simulacao", "simulação": "simulacao",
                   "test": "ensaio", "inspection": "inspecao", "inspeção": "inspecao",
                   "demonstration": "demonstracao", "demonstração": "demonstracao", "review": "revisao",
                   "review-of-design": "revisao", "revisão": "revisao"}
FIDELITIES = ("N0", "N1", "N2", "N3")
SOURCE_KINDS = ("missao", "regulamento", "norma", "sora", "utilizador", "derivado")
COMPARISONS = ("min", "max", "target", "bool", "categoria", "objetivo")
_EPS = 1e-9  # margem relativa numérica: «exatamente no limiar» conta como cumprido quando a tolerância é 0
MATRIX_FILES = ("verification_matrix.json", "verification_matrix.md", "verification_matrix.csv")


class VerificationError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ modelo
@dataclass(frozen=True)
class TracedRequirement:
    """Um requisito rastreável. ``threshold`` e ``goal`` em SI (ou str/bool para categorias/veredictos)."""

    id: str
    text: str
    quantity: str
    comparison: str
    threshold: float | str | bool | None = None
    unit: str = ""
    display: str = ""  # limiar como escrito pelo utilizador, p. ex. "300 m"
    goal: float | None = None  # objetivo (melhor do que o limiar), opcional
    tolerance: float = 0.0  # relativa ao |limiar|
    tolerance_source: str = ""
    source: str = "missao"
    source_kind: str = "missao"
    parents: tuple[str, ...] = ()
    method: str = "analise"
    fidelity: str = "N0"
    evaluator: str | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            raise VerificationError("requisito sem ID")
        if self.comparison not in COMPARISONS:
            raise VerificationError(f"{self.id}: comparação '{self.comparison}' não está em {COMPARISONS}")
        if self.method not in METHODS:
            raise VerificationError(f"{self.id}: método '{self.method}' não está em {METHODS}")
        if self.fidelity not in FIDELITIES:
            raise VerificationError(f"{self.id}: fidelidade '{self.fidelity}' não está em {FIDELITIES}")
        if self.source_kind not in SOURCE_KINDS:
            raise VerificationError(f"{self.id}: tipo de origem '{self.source_kind}' não está em {SOURCE_KINDS}")
        if not (self.tolerance >= 0.0 and math.isfinite(self.tolerance)):
            raise VerificationError(f"{self.id}: tolerância tem de ser ≥ 0 e finita")
        if self.comparison in ("min", "max", "target"):
            if not isinstance(self.threshold, (int, float)) or isinstance(self.threshold, bool) \
                    or not math.isfinite(float(self.threshold)):
                raise VerificationError(f"{self.id}: comparação '{self.comparison}' precisa de limiar numérico")


@dataclass(frozen=True)
class Evidence:
    """O que um avaliador devolve. ``ran=False`` → a etapa não correu (nao_avaliado). ``value=None`` e
    ``ok=None`` com ``ran=True`` → desconhecido."""

    value: float | str | bool | None = None
    unit: str = ""
    ok: bool | None = None  # veredicto do próprio avaliador (comparações bool/categoria)
    message: str = ""
    pointer: str = ""  # caminho dentro do ficheiro de evidência, p. ex. "performance.requirements[3]"
    ran: bool = True
    fidelity: str | None = None  # fidelidade efetiva desta corrida, se o avaliador a souber
    display: str = ""  # valor como o avaliador o mostra (unidade do utilizador), p. ex. "1233 km"
    resolution: float = 0.0  # resolução numérica relativa do avaliador; banda = max(tolerância declarada, isto)
    resolution_source: str = ""
    file: str = ""  # ficheiro de evidência próprio (relativo à pasta de saída); vazio = o do contexto


@dataclass
class VerificationContext:
    result: Mapping[str, Any]
    evidence_file: str = ""  # caminho do ficheiro de resultados (p. ex. result.json)
    evidence_sha256: str | None = None
    output_dir: str | None = None
    provenance_fingerprint: str | None = None
    provenance_file: str | None = None
    provenance_sha256: str | None = None
    domain: str = ""
    extra: dict[str, Any] = field(default_factory=dict)  # objetos do domínio (p. ex. a missão carregada)


EvaluatorFn = Callable[[TracedRequirement, VerificationContext, str], Evidence]
EvidenceLister = Callable[[VerificationContext], list[str]]


@dataclass(frozen=True)
class Evaluator:
    """``name`` exato (``"sizing:stall_speed"``) ou prefixo terminado em ``:`` (``"perf:"``); a função recebe o
    sufixo como 3.º argumento."""

    name: str
    fn: EvaluatorFn
    description: str
    method: str = "analise"
    fidelity: str = "N0"
    reference: str = ""
    domains: tuple[str, ...] = ("core",)


EVALUATORS: dict[str, Evaluator] = {}
_LISTERS: dict[str, list[EvidenceLister]] = {}
_DEFAULT_EVALUATORS: dict[str, dict[str, tuple[str, str, str]]] = {}


def register_evaluator(ev: Evaluator, overwrite: bool = False) -> Evaluator:
    if ev.name in EVALUATORS and not overwrite:
        raise KeyError(f"avaliador '{ev.name}' já registado")
    if ev.method not in METHODS or ev.fidelity not in FIDELITIES:
        raise VerificationError(f"avaliador '{ev.name}': método/fidelidade inválidos")
    EVALUATORS[ev.name] = ev
    return ev


def register_evidence_lister(domain: str, fn: EvidenceLister) -> None:
    """Uma função que lista os nomes de avaliador com evidência disponível numa corrida (para a cobertura:
    «avaliadores sem requisito»)."""
    _LISTERS.setdefault(domain, []).append(fn)


def register_default_evaluator(domain: str, key: str, evaluator: str, method: str, fidelity: str) -> None:
    """Avaliador por omissão de um tipo de requisito da missão (``requirements:``) num domínio."""
    _DEFAULT_EVALUATORS.setdefault(domain, {})[key] = (evaluator, method, fidelity)


def default_evaluator(domain: str, key: str) -> tuple[str, str, str] | None:
    return _DEFAULT_EVALUATORS.get(domain, {}).get(key)


def resolve_evaluator(name: str | None) -> tuple[Evaluator, str] | None:
    if not name:
        return None
    if name in EVALUATORS:
        return EVALUATORS[name], ""
    if ":" in name:
        pre, _, rest = name.partition(":")
        ev = EVALUATORS.get(pre + ":")
        if ev is not None:
            return ev, rest
    return None


# ------------------------------------------------------------------------------- avaliador genérico do núcleo
def json_path(obj: Any, path: str) -> Any:
    """``a.b[2].c`` num JSON; ``KeyError`` se não existir."""
    cur: Any = obj
    for part in path.replace("]", "").split("."):
        if not part:
            continue
        name, *idx = part.split("[")
        if name:
            if not isinstance(cur, Mapping) or name not in cur:
                raise KeyError(path)
            cur = cur[name]
        for i in idx:
            if not isinstance(cur, list) or not -len(cur) <= int(i) < len(cur):
                raise KeyError(path)
            cur = cur[int(i)]
    return cur


def _eval_result_path(req: TracedRequirement, ctx: VerificationContext, path: str) -> Evidence:
    try:
        v = json_path(ctx.result, path)
    except (KeyError, ValueError):
        return Evidence(ran=False, message=f"'{path}' não existe nos resultados (etapa não correu?)", pointer=path)
    if v is None:
        return Evidence(None, req.unit, message=f"'{path}' é nulo", pointer=path)
    if isinstance(v, (bool, str)):
        return Evidence(v, req.unit, pointer=path)
    if isinstance(v, (int, float)):
        return Evidence(float(v), req.unit, pointer=path)
    return Evidence(None, req.unit, message=f"'{path}' não é escalar", pointer=path)


def _eval_file_path(req: TracedRequirement, ctx: VerificationContext, arg: str) -> Evidence:
    """``ficheiro:<relativo>#<caminho.json>`` — evidência noutro JSON da pasta de saída (p. ex. a saída de
    ``acdt simulate`` ou ``acdt certify`` copiada para lá). Ficheiro em falta → nao_avaliado."""
    rel, _, path = arg.partition("#")
    if not ctx.output_dir or not rel:
        return Evidence(ran=False, message="sem pasta de saída ou ficheiro na referência")
    f = Path(ctx.output_dir) / rel
    if not f.is_file():
        return Evidence(ran=False, message=f"'{rel}' não existe na pasta de saída (corrida que o produz não feita)")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as ex:
        return Evidence(None, message=f"'{rel}' ilegível: {ex}", file=rel)
    sub = VerificationContext(result=data, output_dir=ctx.output_dir, domain=ctx.domain)
    ev = _eval_result_path(req, sub, path)
    return Evidence(ev.value, ev.unit, ev.ok, ev.message, ev.pointer, ev.ran, file=rel)


register_evaluator(Evaluator("resultado:", _eval_result_path,
                             "valor escalar num caminho do ficheiro de resultados (unidade = a do requisito, SI)"))
register_evaluator(Evaluator("ficheiro:", _eval_file_path,
                             "valor escalar noutro JSON da pasta de saída: ficheiro:<relativo>#<caminho>"))


# ------------------------------------------------------------------------------------------------ motor
@dataclass
class MatrixRow:
    id: str
    text: str
    source: str
    source_kind: str
    parents: list[str]
    children: list[str]
    quantity: str
    comparison: str
    threshold: Any
    display: str
    unit: str
    goal: float | None
    value: Any
    value_display: str
    margin: float | None  # relativa; > 0 = folga (min/max); para target, tolerância − desvio
    tolerance: float
    status: str
    meets_goal: bool | None
    evaluator: str | None
    method: str
    fidelity_required: str
    fidelity_evaluated: str | None
    evidence: str
    evidence_sha256: str | None
    provenance_fingerprint: str | None
    provenance_sha256: str | None
    message: str
    aggregated_from_children: bool = False
    children_worst: str | None = None  # pior estado dos filhos (visível mesmo quando o pai tem avaliador próprio)


def _numeric(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    f = float(x)
    return f if math.isfinite(f) else None


def classify(req: TracedRequirement, ev: Evidence) -> tuple[str, float | None, str]:
    """Estado, margem relativa e nota a partir da evidência. Regra única para todos os domínios."""
    if not ev.ran:
        return "nao_avaliado", None, ev.message or "avaliador não correu"
    if req.comparison in ("bool", "categoria"):
        if ev.ok is not None:
            return ("passa" if ev.ok else "falha"), None, ev.message
        if req.comparison == "categoria" and isinstance(ev.value, str) and req.threshold is not None:
            return ("passa" if ev.value == req.threshold else "falha"), None, ev.message
        if req.comparison == "bool" and isinstance(ev.value, bool):
            want = True if req.threshold is None else bool(req.threshold)
            return ("passa" if ev.value == want else "falha"), None, ev.message
        return "desconhecido", None, ev.message or "sem veredicto"
    if req.comparison in ("min", "max", "target") and _numeric(ev.value) is None and ev.ok is not None:
        return ("passa" if ev.ok else "falha"), None, \
            (ev.message + "; " if ev.message else "") + "veredicto do avaliador (sem valor numérico)"
    if req.comparison == "objetivo":
        return "nao_avaliado", None, (ev.message + "; " if ev.message else "") + "objetivo sem limiar: só reportado"
    v = _numeric(ev.value)
    if v is None:
        return "desconhecido", None, ev.message or "sem valor numérico"
    thr = float(req.threshold)  # type: ignore[arg-type]  # garantido em __post_init__
    scale = abs(thr) if thr != 0.0 else 1.0
    tol = max(req.tolerance, ev.resolution)
    if req.comparison == "max":
        m = (thr - v) / scale
    elif req.comparison == "min":
        m = (v - thr) / scale
    else:  # target: dentro da tolerância passa; sem tolerância declarada compara com _EPS
        dev = abs(v - thr) / scale
        m = tol - dev
        return ("passa" if dev <= max(tol, _EPS) else "falha"), m, ev.message
    if tol > 0.0 and abs(m) <= tol:
        why = "tolerância declarada" if req.tolerance >= ev.resolution else \
            f"resolução do avaliador {ev.resolution:g}" + (f" ({ev.resolution_source})" if ev.resolution_source else "")
        return "no_limite", m, (ev.message + "; " if ev.message else "") + f"dentro da banda ±{tol:g} ({why})"
    if m >= -_EPS:
        return "passa", m, ev.message
    return "falha", m, ev.message


def _meets_goal(req: TracedRequirement, value: Any) -> bool | None:
    v = _numeric(value)
    if req.goal is None or v is None:
        return None
    if req.comparison == "max":
        return v <= req.goal
    if req.comparison == "min":
        return v >= req.goal
    return None


def check_tree(reqs: Sequence[TracedRequirement]) -> list[str]:
    """Problemas estruturais: IDs repetidos, pais desconhecidos, ciclos."""
    issues: list[str] = []
    ids = [r.id for r in reqs]
    seen: set[str] = set()
    for i in ids:
        if i in seen:
            issues.append(f"ID repetido: {i}")
        seen.add(i)
    by_id = {r.id: r for r in reqs}
    for r in reqs:
        for p in r.parents:
            if p not in by_id:
                issues.append(f"{r.id}: pai desconhecido '{p}'")
    state: dict[str, int] = {}  # 1 = em visita, 2 = fechado (DFS pelos pais)

    def visit(i: str) -> bool:
        if state.get(i) == 1:
            return True
        if state.get(i) == 2 or i not in by_id:
            return False
        state[i] = 1
        cyc = any(visit(p) for p in by_id[i].parents)
        state[i] = 2
        return cyc

    for r in reqs:
        state.clear()
        if visit(r.id):
            issues.append(f"ciclo na árvore de requisitos através de {r.id}")
    return sorted(set(issues))


def _fid_rank(f: str | None) -> int:
    return FIDELITIES.index(f) if f in FIDELITIES else -1


def evaluate(reqs: Sequence[TracedRequirement], ctx: VerificationContext) -> list[MatrixRow]:
    """Avalia todos os requisitos. Pais sem avaliador próprio herdam o pior estado dos filhos (agregação)."""
    children: dict[str, list[str]] = {r.id: [] for r in reqs}
    for r in reqs:
        for p in r.parents:
            if p in children:
                children[p].append(r.id)
    rows: dict[str, MatrixRow] = {}
    for r in reqs:
        res = resolve_evaluator(r.evaluator)
        fid_eval: str | None = None
        if r.evaluator is None:
            ev = Evidence(ran=False, message="sem avaliador declarado")
        elif res is None:
            ev = Evidence(ran=False, message=f"avaliador '{r.evaluator}' não registado")
        else:
            evr, arg = res
            try:
                ev = evr.fn(r, ctx, arg)
            except Exception as ex:  # noqa: BLE001 — um avaliador partido é desconhecido, nunca passa
                ev = Evidence(None, message=f"avaliador falhou: {type(ex).__name__}: {ex}")
            fid_eval = ev.fidelity or evr.fidelity
        status, margin, msg = classify(r, ev)
        if status == "passa" and _fid_rank(fid_eval) < _fid_rank(r.fidelity):
            status = "nao_avaliado"
            msg = (msg + "; " if msg else "") + f"fidelidade {fid_eval} abaixo da exigida {r.fidelity}"
        evid, esha = "", None
        if ev.ran and ev.file:
            evid = ev.file + (f"#{ev.pointer}" if ev.pointer else "")
            fp = Path(ctx.output_dir or ".") / ev.file
            if fp.is_file():
                from acdt.core.provenance import sha256_file
                esha = sha256_file(fp)
        elif ev.ran and ctx.evidence_file:
            evid, esha = ctx.evidence_file + (f"#{ev.pointer}" if ev.pointer else ""), ctx.evidence_sha256
        rows[r.id] = MatrixRow(
            id=r.id, text=r.text, source=r.source, source_kind=r.source_kind, parents=list(r.parents),
            children=children[r.id], quantity=r.quantity, comparison=r.comparison, threshold=r.threshold,
            display=r.display, unit=ev.unit or r.unit, goal=r.goal, value=ev.value, margin=margin,
            tolerance=r.tolerance, status=status, meets_goal=_meets_goal(r, ev.value), evaluator=r.evaluator,
            method=r.method, fidelity_required=r.fidelity, fidelity_evaluated=fid_eval, evidence=evid,
            evidence_sha256=esha, value_display=ev.display,
            provenance_fingerprint=ctx.provenance_fingerprint, provenance_sha256=ctx.provenance_sha256,
            message=msg)
    # agregação dos filhos (de baixo para cima; a árvore é pequena, itera até estabilizar)
    for _ in range(len(reqs) + 1):
        changed = False
        for r in reqs:
            row = rows[r.id]
            if r.evaluator is not None or not row.children:
                continue
            kids = [rows[c].status for c in row.children]
            worst = min(kids, key=lambda s: _SEVERITY[s])
            if row.status != worst or not row.aggregated_from_children:
                row.status, row.aggregated_from_children = worst, True
                row.message = f"agregado dos filhos ({', '.join(row.children)}): pior estado = {worst}"
                changed = True
        if not changed:
            break
    for row in rows.values():
        if row.children:
            row.children_worst = min((rows[c].status for c in row.children), key=lambda s: _SEVERITY[s])
    return [rows[r.id] for r in reqs]


def coverage(reqs: Sequence[TracedRequirement], rows: Sequence[MatrixRow],
             available: Iterable[str]) -> dict[str, Any]:
    """Cobertura: requisitos sem avaliador (nem filhos), avaliadores não registados, evidência sem requisito."""
    used = {r.evaluator for r in reqs if r.evaluator}
    no_eval = [r.id for r in reqs if r.evaluator is None and not any(r.id in q.parents for q in reqs)]
    unknown = sorted({r.evaluator for r in reqs if r.evaluator and resolve_evaluator(r.evaluator) is None})
    orphan = sorted(set(available) - used)
    counts = {s: sum(1 for x in rows if x.status == s) for s in STATUSES}
    return {"requisitos": len(reqs), "por_estado": counts, "requisitos_sem_avaliador": no_eval,
            "avaliadores_nao_registados": unknown, "avaliadores_sem_requisito": orphan,
            "fracao_avaliada": (sum(counts[s] for s in ("passa", "falha", "no_limite")) / len(reqs)) if reqs else None}


def available_evidence(ctx: VerificationContext) -> list[str]:
    out: list[str] = []
    for fn in _LISTERS.get(ctx.domain, []):
        out += fn(ctx)
    return sorted(set(out))


# ------------------------------------------------------------------------------------------------ proveniência
FINGERPRINT_KEYS = ("acdt", "python", "packages", "platform", "tools", "inputs", "seeds")


def provenance_fingerprint(record: Mapping[str, Any]) -> str:
    """SHA-256 canónico do registo ``acdt.provenance/1`` sem datas, notas, comando nem manifesto de saídas:
    igual quando calculado durante a corrida e depois a partir do ``provenance.json``."""
    from acdt.core.provenance import canonical_hash

    git = dict((record.get("acdt") or {}).get("git") or {})
    sub: dict[str, Any] = {
        "acdt_version": (record.get("acdt") or {}).get("version"),
        "commit": git.get("commit"), "dirty": git.get("dirty"), "dirty_diff_sha256": git.get("dirty_diff_sha256"),
        "python": (record.get("python") or {}).get("version"),
        "packages": record.get("packages") or {},
        "platform": {k: v for k, v in (record.get("platform") or {}).items() if k in ("system", "machine")},
        "tools": {n: (t or {}).get("sha256") for n, t in sorted((record.get("tools") or {}).items())},
        "inputs": sorted((i or {}).get("sha256") or "" for i in record.get("inputs") or []),
        "seeds": record.get("seeds") or {},
    }
    return canonical_hash(sub)


def context_from_output(outdir: str | Path, result_name: str = "result.json", domain: str = "") -> VerificationContext:
    """Contexto a partir de uma pasta de saída (``acdt verify``): resultados + registo de proveniência se existir."""
    from acdt.core import provenance as P

    d = Path(outdir)
    rf = d / result_name
    if not rf.is_file():
        raise FileNotFoundError(f"{rf} não existe")
    result = json.loads(rf.read_text(encoding="utf-8"))
    ctx = VerificationContext(result=result, evidence_file=rf.name, evidence_sha256=P.sha256_file(rf),
                              output_dir=str(d), domain=domain)
    pf = d / P.SIDECAR_DIR_NAME
    if pf.is_file():
        try:
            rec = json.loads(pf.read_text(encoding="utf-8"))
            ctx.provenance_fingerprint = provenance_fingerprint(rec)
            ctx.provenance_file, ctx.provenance_sha256 = pf.name, P.sha256_file(pf)
        except (OSError, ValueError):
            pass
    return ctx


# ------------------------------------------------------------------------------------------------ escrita
def build_matrix(reqs: Sequence[TracedRequirement], ctx: VerificationContext,
                 tree_issues: Sequence[str] = ()) -> dict[str, Any]:
    rows = evaluate(reqs, ctx)
    cov = coverage(reqs, rows, available_evidence(ctx))
    return {"schema": SCHEMA, "domain": ctx.domain, "evidence_file": ctx.evidence_file,
            "evidence_sha256": ctx.evidence_sha256,
            "provenance": {"fingerprint": ctx.provenance_fingerprint, "file": ctx.provenance_file,
                           "sha256": ctx.provenance_sha256},
            "statuses": list(STATUSES), "tree_issues": list(tree_issues) + check_tree(reqs),
            "coverage": cov, "rows": [asdict(r) for r in rows]}


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "sim" if x else "não"
    if isinstance(x, float):
        return f"{x:.4g}"
    return str(x)


CSV_COLUMNS = ("id", "status", "text", "source", "parents", "quantity", "comparison", "threshold", "display", "unit",
               "value", "value_display", "margin", "tolerance", "goal", "meets_goal", "evaluator", "method", "fidelity_required",
               "fidelity_evaluated", "children_worst", "evidence", "evidence_sha256", "provenance_fingerprint", "message")


PROB_CSV_COLUMNS = ("p_passa", "p_passa_ic", "p_no_limite", "p_falha", "estado_probabilistico")


def to_csv(matrix: Mapping[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cols = CSV_COLUMNS + (PROB_CSV_COLUMNS if any("estado_probabilistico" in r for r in matrix["rows"]) else ())
    w.writerow(cols)
    for r in matrix["rows"]:
        w.writerow([";".join(str(x) for x in r.get(c)) if isinstance(r.get(c), list)
                    else ("" if r.get(c) is None else r.get(c)) for c in cols])
    return buf.getvalue()


def _fmt_p(p: Any) -> str:
    if isinstance(p, list) and len(p) == 2:
        return f"[{float(p[0]):.3f}, {float(p[1]):.3f}]"
    return "—" if p is None else f"{float(p):.3f}"


def attach_probabilistic(matrix: Mapping[str, Any], prob: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Cópia da matriz com as colunas probabilísticas de ``acdt uq`` (``p_passa``, ``p_passa_ic``,
    ``estado_probabilistico``). O ``status`` determinístico **não muda**. Requisitos sem resultado probabilístico
    ficam ``nao_avaliado`` na coluna nova. Pais sem avaliador próprio: pior estado probabilístico dos filhos."""
    order = ("prob_falha", "desconhecido", "nao_avaliado", "inconclusivo", "prob_no_limite", "prob_passa")
    rows = []
    by: dict[str, dict[str, Any]] = {}
    for r in matrix["rows"]:
        q = dict(r)
        pr = prob.get(str(r["id"]))
        if pr is not None:
            q["p_passa"] = pr.get("p_passa")
            q["p_passa_ic"] = pr.get("p_passa_ic")
            q["p_no_limite"] = pr.get("p_no_limite")
            q["p_falha"] = pr.get("p_falha")
            q["estado_probabilistico"] = pr.get("estado_probabilistico", "nao_avaliado")
        else:
            q["p_passa"], q["p_passa_ic"], q["estado_probabilistico"] = None, None, "nao_avaliado"
            q["p_no_limite"], q["p_falha"] = None, None
        rows.append(q)
        by[str(q["id"])] = q
    for _ in range(len(rows) + 1):
        changed = False
        for q in rows:
            if q.get("evaluator") is None and q.get("children"):
                kids = [by[c]["estado_probabilistico"] for c in q["children"] if c in by]
                if kids:
                    w = min(kids, key=order.index)
                    if q["estado_probabilistico"] != w:
                        q["estado_probabilistico"] = w
                        changed = True
        if not changed:
            break
    out = dict(matrix)
    out["rows"] = rows
    out["probabilistic"] = {"schema": "acdt.uq/1", "statuses": list(order),
                            "nota": "colunas de acdt uq; o estado determinístico (status) não muda"}
    return out


def to_markdown(matrix: Mapping[str, Any], title: str = "Matriz de verificação") -> str:
    cov = matrix["coverage"]
    pv = matrix["provenance"]
    lines = [f"# {title}", "",
             f"Formato `{matrix['schema']}`. Evidência: `{matrix['evidence_file']}` "
             f"(SHA-256 `{_fmt(matrix['evidence_sha256'])[:12]}`). Proveniência: impressão digital "
             f"`{_fmt(pv['fingerprint'])[:12]}`" + (f", `{pv['file']}` SHA-256 `{pv['sha256'][:12]}`"
                                                    if pv.get("sha256") else " (registo escrito no fim da corrida)")
             + ".", "",
             "Estados: **passa**, **falha**, **no_limite** (dentro da tolerância declarada), **nao_avaliado** "
             "(sem avaliador ou etapa não correu), **desconhecido** (correu sem valor). Não avaliado ≠ passa.", "",
             "| Estado | N.º |", "|---|---|"]
    lines += [f"| {s} | {cov['por_estado'][s]} |" for s in STATUSES]
    prob = any("estado_probabilistico" in r for r in matrix["rows"])
    lines += ["", "| ID | Estado | Requisito | Origem | Limiar | Valor | Margem | Avaliador | Método | Fid. "
                  "(exig./aval.) | Nota |" + (" P(passa) | Estado prob. |" if prob else ""),
              "|---|---|---|---|---|---|---|---|---|---|---|" + ("---|---|" if prob else "")]
    for r in matrix["rows"]:
        thr = r["display"] or (f"{r['comparison']} {_fmt(r['threshold'])}")
        val = r.get("value_display") or (_fmt(r["value"]) + (f" {r['unit']}" if r["value"] is not None and r["unit"]
                                                             else ""))
        mg = "—" if r["margin"] is None else (f"{100 * r['margin']:+.1f} %" if abs(r["margin"]) >= 1e-3
                                              else f"{100 * r['margin']:+.3f} %")
        if r.get("children_worst") and r["children_worst"] != "passa" and not r.get("aggregated_from_children"):
            r = {**r, "message": f"{r['message']} [filhos: {r['children_worst']}]".strip()}
        par = f" ← {', '.join(r['parents'])}" if r["parents"] else ""
        note = str(r["message"]).replace("|", "/").replace("\n", " ")
        lines.append(f"| {r['id']}{par} | {r['status']} | {r['text']} | {r['source']} | {thr} | {val} | {mg} | "
                     f"{_fmt(r['evaluator'])} | {r['method']} | {r['fidelity_required']}/"
                     f"{_fmt(r['fidelity_evaluated'])} | {note[:160]} |" + (f" {_fmt_p(r.get('p_passa'))} | "
                                                                             f"{_fmt(r.get('estado_probabilistico'))} |"
                                                                             if prob else ""))
    lines += ["", "## Cobertura", "",
              f"* Requisitos sem avaliador (nem filhos): {', '.join(cov['requisitos_sem_avaliador']) or 'nenhum'}",
              f"* Avaliadores não registados: {', '.join(cov['avaliadores_nao_registados']) or 'nenhum'}",
              f"* Evidência sem requisito ({len(cov['avaliadores_sem_requisito'])}): "
              + (", ".join(f"`{x}`" for x in cov["avaliadores_sem_requisito"]) or "nenhuma")]
    if matrix["tree_issues"]:
        lines += ["", "## Problemas na árvore de requisitos", ""] + [f"* {x}" for x in matrix["tree_issues"]]
    return "\n".join(lines) + "\n"


def write_matrix(matrix: Mapping[str, Any], outdir: str | Path) -> list[Path]:
    d = Path(outdir)
    d.mkdir(parents=True, exist_ok=True)
    js, md, cs = (d / n for n in MATRIX_FILES)
    js.write_text(json.dumps(matrix, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    md.write_text(to_markdown(matrix), encoding="utf-8")
    cs.write_text(to_csv(matrix), encoding="utf-8")
    return [js, md, cs]


# ------------------------------------------------------------------------------------------------ leitura (YAML)
from acdt.core.requirements import TRACE_KEYS  # noqa: E402  (uma só lista)


def _parents(v: Any) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return (v,)
    return tuple(str(x) for x in v)


def normalise_method(m: Any) -> str:
    s = str(m or "analise").strip().lower()
    return _METHOD_ALIASES.get(s, s)


def from_mission_requirement(key: str, sense: str, value: Any, unit: str, raw: Any, trace: Mapping[str, Any],
                             domain: str, default_id: str, si_unit: str = "") -> TracedRequirement:
    """Requisito da secção ``requirements:`` da missão → :class:`TracedRequirement`. Sem ``id`` explícito o ID é
    ``default_id`` (estável: ``REQ-<chave>[-<sentido>]``). Sem ``evaluator`` usa-se o avaliador por omissão do
    domínio para a chave, se houver."""
    dflt = default_evaluator(domain, key)
    if sense == "objective":
        comp: str = "objetivo"
    elif isinstance(value, str):
        comp = "categoria"
    else:
        comp = sense
    goal = trace.get("goal")
    return TracedRequirement(
        id=str(trace.get("id") or default_id),
        text=str(trace.get("text") or f"{key} {sense} {raw} {unit}".strip()),
        quantity=key, comparison=comp, threshold=value if comp != "objetivo" else None,
        unit=si_unit, display=f"{'≤' if sense == 'max' else '≥' if sense == 'min' else '='} {raw} {unit}".strip()
        if comp in ("min", "max", "target") else str(raw),
        goal=float(goal) if isinstance(goal, (int, float)) else None,
        tolerance=float(trace.get("tolerance", 0.0)), tolerance_source=str(trace.get("tolerance_source", "")),
        source=str(trace.get("source", "missao")), source_kind=str(trace.get("source_kind", "missao")),
        parents=_parents(trace.get("parents", trace.get("parent"))),
        method=normalise_method(trace.get("method", dflt[1] if dflt else "analise")),
        fidelity=str(trace.get("fidelity", dflt[2] if dflt else "N0")),
        evaluator=trace.get("evaluator", dflt[0] if dflt else None),
        notes=str(trace.get("notes", "")))


def from_dict(d: Mapping[str, Any], unit_to_si: Callable[[float, str], tuple[float, str]] | None = None
              ) -> TracedRequirement:
    """Requisito derivado/regulamentar da secção ``verification.requirements``. Campos: id, text, source,
    source_kind, parent(s), quantity, comparison, threshold (+ unit), goal, tolerance, method, fidelity,
    evaluator, notes. ``unit_to_si(valor, unidade) → (valor_si, unidade_si)`` converte limiar e objetivo."""
    known = set(TRACE_KEYS) | {"quantity", "comparison", "threshold", "unit", "dimension"}
    extra = set(d) - known
    if extra:
        raise VerificationError(f"{d.get('id', '?')}: campos desconhecidos {sorted(extra)}")
    comp = str(d.get("comparison", "bool"))
    thr: Any = d.get("threshold")
    goal: Any = d.get("goal")
    unit = str(d.get("unit", ""))
    si_unit = unit
    disp = ""
    if comp in ("min", "max", "target") and isinstance(thr, (int, float)) and not isinstance(thr, bool):
        disp = f"{'≤' if comp == 'max' else '≥' if comp == 'min' else '='} {thr:g} {unit}".strip()
        conv = unit_to_si or (lambda v, u: si_convert(v, u, d.get("dimension")))
        if unit:
            thr, si_unit = conv(float(thr), unit)
            if isinstance(goal, (int, float)):
                goal = conv(float(goal), unit)[0]
    elif comp in ("bool", "categoria"):
        disp = "verdadeiro" if thr is None and comp == "bool" else str(thr)
    return TracedRequirement(
        id=str(d.get("id", "")), text=str(d.get("text", "")), quantity=str(d.get("quantity", "")),
        comparison=comp, threshold=thr, unit=si_unit, display=disp,
        goal=float(goal) if isinstance(goal, (int, float)) else None,
        tolerance=float(d.get("tolerance", 0.0)), tolerance_source=str(d.get("tolerance_source", "")),
        source=str(d.get("source", "utilizador")), source_kind=str(d.get("source_kind", "utilizador")),
        parents=_parents(d.get("parents", d.get("parent"))), method=normalise_method(d.get("method")),
        fidelity=str(d.get("fidelity", "N0")), evaluator=d.get("evaluator"), notes=str(d.get("notes", "")))


def si_convert(value: float, unit: str, dimension: Any = None) -> tuple[float, str]:
    """Valor numa unidade → (SI, unidade SI). Sem ``dimension`` infere-a quando a unidade é inequívoca."""
    from acdt.core import units

    if dimension:
        dims = [str(dimension)]
    else:
        dims = [dm for dm, tb in units._UNITS.items() if unit in tb and dm not in ("category", "strain")]
    if len(dims) != 1:
        raise VerificationError(f"unidade '{unit}' ambígua ou desconhecida ({dims}); declare 'dimension'")
    try:
        return units.to_si(value, unit, dims[0]), units.default_unit(dims[0])
    except units.UnitError as ex:
        raise VerificationError(str(ex)) from ex


def requirements_from_mission(reqset: Iterable[Any], section: Mapping[str, Any] | None, domain: str
                              ) -> list[TracedRequirement]:
    """Requisitos da missão (``RequirementSet``, com ``trace``) + ``verification.requirements`` (derivados,
    regulamentares, SORA, utilizador). IDs por omissão estáveis: ``REQ-<chave>`` (``-<sentido>`` se a mesma
    chave tiver vários sentidos)."""
    from acdt.core import units
    from acdt.core.requirements import REGISTRY

    rs = list(reqset)
    nkey: dict[str, int] = {}
    for r in rs:
        nkey[r.key] = nkey.get(r.key, 0) + 1
    out: list[TracedRequirement] = []
    for r in rs:
        rt = REGISTRY.get(r.key)
        dim = rt.dimension if rt is not None else ""
        si = units.default_unit(dim) if dim and dim != "category" else ""
        did = f"REQ-{r.key}" + (f"-{r.sense}" if nkey[r.key] > 1 else "")
        out.append(from_mission_requirement(r.key, r.sense, r.value, r.unit, r.raw, getattr(r, "trace", {}) or {},
                                            domain, did, si))
    for d in (section or {}).get("requirements", []) or []:
        out.append(from_dict(d))
    return out


def verify(reqs: Sequence[TracedRequirement], ctx: VerificationContext, outdir: str | Path | None = None
           ) -> dict[str, Any]:
    """Matriz completa; escreve JSON/MD/CSV em ``outdir`` se dado."""
    m = build_matrix(reqs, ctx)
    if outdir is not None:
        write_matrix(m, outdir)
    return m
