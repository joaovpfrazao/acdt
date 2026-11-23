# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Falhas de causa comum pelo modelo do fator β (NUREG/CR-5485, Apêndice A, Eq. A.10–A.13).

Fonte conferida na página: Mosleh, Rasmuson e Marshall, *Guidelines on Modeling Common-Cause Failures in
Probabilistic Risk Assessment*, NUREG/CR-5485 (INEEL/EXT-97-01327), NRC, nov. 1998, Apêndice A, p. A-5
(modelo de Fleming, 1975). Para um grupo de m componentes semelhantes, com probabilidade total de falha Q_t de
cada um:

    Q_1 = (1 − β) Q_t           (falha independente de um componente)
    Q_m = β Q_t                 (evento de causa comum: falham os m componentes)
    Q_k = 0,  1 < k < m

e Q_t = Q_1 + Q_m (Eq. A.12). O texto diz que o modelo assume que, quando ocorre o evento de causa comum, falham
todos os componentes do grupo, e que é ligeiramente conservador em redundâncias pequenas.

Ligação à árvore de falhas (ARP4761 / NUREG-0492): cada evento básico C_i do grupo passa a uma porta OR de dois
eventos, o independente I_i com q = (1 − β) Q_t e o evento partilhado CCF com q = β Q_t. O CCF é o mesmo evento
em todas as portas, por isso a probabilidade exata do topo (decomposição de Shannon em
:class:`acdt.core.safety.fta.FaultTree`) já o conta uma vez. Funciona com AND, OR e k-de-n.

β não tem omissão: tem de vir declarado com a sua fonte (``beta_source``). Sem β o resultado com causa comum fica
desconhecido; o valor só com avarias independentes é um limite inferior da probabilidade de falha, não o resultado.
O grupo tem de ter Q_t iguais (o modelo é para componentes semelhantes); Q_t diferentes → ``nao_avaliado``.

Modelos de vários parâmetros (mesma fonte, conferidos nas páginas 40–42 e A-9–A-11 do PDF público):

* MGL (Multiple Greek Letter), Eq. 5.13: Q_k = 1/C(m−1, k−1) · (Π_{i=1..k} ρ_i) · (1 − ρ_{k+1}) · Q_t, com
  ρ_1 = 1, ρ_2 = β, ρ_3 = γ, ρ_4 = δ, …, ρ_{m+1} = 0 (Eq. 5.11 para m = 3). O fator β é o caso particular.
* Fator α, ensaio escalonado, Eq. 5.6: Q_k = α_k Q_t / C(m−1, k−1).
* Fator α, ensaio não escalonado, Eq. 5.7 (= Eq. A.23, porque m/C(m, k) = k/C(m−1, k−1)):
  Q_k = k/C(m−1, k−1) · α_k/α_t · Q_t, com α_t = Σ k α_k (Eq. 5.9 / A.24).
* Conversão MGL ↔ α (ensaio escalonado), Tabela A-2: α_k = (Π_{i≤k} ρ_i)(1 − ρ_{k+1}).

Q_k é a probabilidade de um evento de causa comum que envolve k componentes específicos. Na FTA cada evento do
grupo passa a OR(independente Q_1, todos os eventos CCF de ordem k ≥ 2 que o contêm), um evento partilhado por
cada subconjunto de k componentes (o modelo de parâmetros básicos da secção 5.3). O exemplo numérico da Eq. 5.10
(Q_3 = 3 α_3 Q_t «escalonado») não bate com a Eq. 5.6 (dá α_3 Q_t); usa-se a equação geral e o 3 α_3/α_t Q_t é
o resultado da Eq. 5.7 (não escalonado). Os α e os ρ têm de vir declarados com fonte; não há omissão. Os valores
de β da IEC 61508-6 Anexo D não estão aqui: a norma não é pública e não foi possível conferi-los.
"""
from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Mapping, Sequence

from acdt.core.safety.fta import BasicEvent, FaultTree, Gate

SOURCE = ("NUREG/CR-5485 (Mosleh, Rasmuson e Marshall, NRC, nov. 1998) Apêndice A, Eq. A.10–A.13, p. A-5 "
          "(modelo do fator β de Fleming, 1975)")
_REL_EQUAL = 1e-9
SOURCE_MGL = ("NUREG/CR-5485 (NRC, 1998) §5.3, Eq. 5.11 e 5.13, pp. 41–42 (modelo MGL); conversão α↔MGL "
              "Tabela A-2, p. A-11")
SOURCE_ALPHA = ("NUREG/CR-5485 (NRC, 1998) §5.3, Eq. 5.6–5.9, pp. 40–41; Ap. A Eq. A.21–A.24, p. A-9 "
                "(modelo do fator α)")
M_MAX_FTA = 6          # 2^m − m − 1 eventos CCF na árvore (57 para m = 6): avaliação exata ainda barata


def _prob(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    v = float(x)
    return v if math.isfinite(v) and 0.0 <= v <= 1.0 else None


def beta_split(q_total: float, beta: float) -> dict[str, float] | None:
    """Eq. A.13: Q_1 = (1 − β) Q_t e Q_m = β Q_t. Entrada inválida → ``None``."""
    q, b = _prob(q_total), _prob(beta)
    if q is None or b is None:
        return None
    return {"Q_t": q, "beta": b, "Q_1": (1.0 - b) * q, "Q_m": b * q}


def apply_beta_factor(tree: FaultTree, group_events: Sequence[str], beta: float, *, group_id: str,
                      t_flight: float = 1.0, source: str = "") -> dict[str, Any]:
    """Substitui, na árvore, cada evento do grupo por OR(independente, CCF partilhado). Altera ``tree``.

    Devolve o bloco do grupo (Q_t, Q_1, Q_m). Q_t diferentes no grupo, menos de dois eventos ou β inválido →
    a árvore não muda e o bloco fica ``nao_avaliado``."""
    out: dict[str, Any] = {"group": group_id, "events": list(group_events), "method": SOURCE, "evaluated": False,
                           "veredicto": "nao_avaliado", "beta": None, "beta_source": source or None, "notes": []}
    ids = list(dict.fromkeys(group_events))
    if len(ids) < 2:
        out["notes"].append("grupo de causa comum com menos de dois eventos")
        return out
    missing = [e for e in ids if e not in tree.events]
    if missing:
        out["notes"].append("eventos fora da árvore: " + ", ".join(missing))
        return out
    qs = [tree.events[e].q(t_flight) for e in ids]
    if max(qs) - min(qs) > _REL_EQUAL * max(max(qs), 1e-300):
        out["notes"].append("Q_t diferentes no grupo: o modelo β é para componentes semelhantes")
        return out
    sp = beta_split(qs[0], beta)
    if sp is None:
        out["notes"].append("β ou Q_t fora de [0, 1]")
        return out
    ccf = f"{group_id}.CCF"
    if ccf in tree.events or ccf in tree.gates:
        out["notes"].append(f"identificador {ccf} já existe na árvore")
        return out
    tree.add_event(BasicEvent(id=ccf, name=f"causa comum {group_id}", prob=sp["Q_m"],
                              source=SOURCE + (f"; β: {source}" if source else "")))
    for e in ids:
        old = tree.events.pop(e)
        ind = f"{e}.I"
        tree.add_event(BasicEvent(id=ind, name=(old.name or e) + " (independente)", prob=sp["Q_1"],
                                  source=SOURCE, latent=old.latent))
        tree.add_gate(Gate(id=e, kind="OR", inputs=[ind, ccf], name=(old.name or e) + " (β)"))
    out.update({"evaluated": True, "veredicto": "validado", "beta": sp["beta"], "Q_t": sp["Q_t"],
                "Q_1": sp["Q_1"], "Q_m": sp["Q_m"], "ccf_event": ccf})
    return out


def redundancy_tree(group_id: str, q_total: float, m: int, k: int) -> FaultTree:
    """Grupo de m componentes semelhantes que falha com k falhas (k = m: redundância ativa, porta AND)."""
    tree = FaultTree(top=f"{group_id}.TOP", name=f"redundância {group_id} ({k} de {m} falham)")
    ev = [tree.add_event(BasicEvent(id=f"{group_id}.{i + 1}", prob=float(q_total))) for i in range(m)]
    kind = "AND" if k == m else ("OR" if k == 1 else "KOFN")
    tree.add_gate(Gate(id=tree.top, kind=kind, inputs=ev, k=k))
    return tree


def _group(raw: Mapping[str, Any], mission_h: float | None) -> dict[str, Any]:
    gid = str(raw.get("id") or "grupo")
    out: dict[str, Any] = {"id": gid, "evaluated": False, "veredicto": "nao_avaliado", "calibracao": "nao_aplicar",
                           "method": SOURCE, "q_top": None, "q_top_independent_only": None, "notes": []}
    m, k = raw.get("m"), raw.get("k_fail", raw.get("m"))
    if not isinstance(m, int) or isinstance(m, bool) or m < 2 or not isinstance(k, int) or isinstance(k, bool) \
            or not 1 <= k <= m:
        out["notes"].append("m (≥ 2) e k_fail (1 ≤ k ≤ m) inteiros em falta ou inválidos")
        return out
    q = _prob(raw.get("q_total"))
    lam = raw.get("lambda_per_h")
    if q is None and lam is not None:
        t = raw.get("t_h", mission_h)
        if isinstance(lam, (int, float)) and not isinstance(lam, bool) and lam >= 0 and \
                isinstance(t, (int, float)) and not isinstance(t, bool) and t >= 0:
            q = -math.expm1(-float(lam) * float(t))  # NUREG-0492: q = 1 − exp(−λ T)
            out["q_from"] = {"lambda_per_h": float(lam), "t_h": float(t)}
    if q is None:
        out["notes"].append("q_total ou (lambda_per_h, t_h) em falta ou inválido: desconhecido, não zero")
        return out
    base = redundancy_tree(gid, q, m, k)
    out["q_top_independent_only"] = base.top_probability()
    out["m"], out["k_fail"], out["Q_t"] = m, k, q
    if raw.get("model") in ("mgl", "alpha"):
        return _multi_group(raw, out, gid, q, m, k)
    if raw.get("model") not in (None, "beta"):
        out["notes"].append("model desconhecido (beta | mgl | alpha)")
        return out
    b = raw.get("beta")
    src = raw.get("beta_source")
    if b is None:
        out["notes"].append("β não declarado: q do topo com causa comum desconhecido; o valor só com avarias "
                            "independentes é limite inferior (eventos raros)")
        out["q_top_bounds"] = {"lo": out["q_top_independent_only"], "hi": None}
        return out
    if not src:
        out["notes"].append("β sem beta_source: não se aplica (nunca se inventa a fonte de β)")
        out["q_top_bounds"] = {"lo": out["q_top_independent_only"], "hi": None}
        return out
    tree = redundancy_tree(gid, q, m, k)
    blk = apply_beta_factor(tree, [f"{gid}.{i + 1}" for i in range(m)], b, group_id=gid, source=str(src))
    out["beta_block"] = blk
    if not blk["evaluated"]:
        out["notes"] += blk["notes"]
        return out
    out["q_top"] = tree.top_probability()
    out["q_top_rare_event"] = tree.rare_event()
    out["minimal_cut_sets"] = [sorted(s) for s in tree.minimal_cut_sets()]
    out["beta"], out["beta_source"] = blk["beta"], str(src)
    out["ccf_share_of_top"] = blk["Q_m"] / out["q_top"] if out["q_top"] else None
    out["evaluated"], out["veredicto"] = True, "validado"
    return out


def common_cause_block(raw: Any, mission_h: float | None) -> dict[str, Any]:
    """Bloco ``common_cause: {groups: [...]}`` da especificação de fiabilidade. Não altera o RBD ativo."""
    if raw is None:
        return {"evaluated": False, "veredicto": "nao_pedido", "beta": None, "method": SOURCE, "groups": []}
    groups = raw.get("groups") if isinstance(raw, Mapping) else None
    if not isinstance(groups, list) or not groups:
        return {"evaluated": False, "veredicto": "nao_avaliado", "beta": None, "method": SOURCE, "groups": [],
                "notes": ["common_cause.groups em falta ou vazio"]}
    rows = [_group(g, mission_h) if isinstance(g, Mapping) else
            {"id": None, "evaluated": False, "veredicto": "nao_avaliado", "notes": ["grupo inválido"]} for g in groups]
    ok = all(r["evaluated"] for r in rows)
    return {"evaluated": ok, "veredicto": "validado" if ok else "nao_avaliado", "calibracao": "nao_aplicar",
            "method": SOURCE, "groups": rows,
            "nota": ("Valida a aplicação das Eq. A.10–A.13 (β), 5.13 (MGL) ou 5.6/5.7 (fator α) com os parâmetros "
                     "declarados; os valores vêm da fonte declarada pelo utilizador e não são verificados aqui. "
                     "Não substitui o RBD ativo.")}


# ------------------------------------------------------------------ MGL e fator α (NUREG/CR-5485 §5.3, Ap. A)
def _floats(xs: Any, n: int) -> list[float] | None:
    if not isinstance(xs, (list, tuple)) or len(xs) != n:
        return None
    out = [_prob(x) for x in xs]
    return None if any(v is None for v in out) else [float(v) for v in out]  # type: ignore[arg-type]


def mgl_q(q_total: float, m: int, greek: Sequence[float]) -> list[float] | None:
    """Eq. 5.13: [Q_1, …, Q_m] para m componentes com ρ_2…ρ_m = ``greek`` (β, γ, δ, …). Inválido → ``None``."""
    q = _prob(q_total)
    if q is None or not isinstance(m, int) or m < 2:
        return None
    g = _floats(list(greek), m - 1)
    if g is None:
        return None
    rho = [1.0] + g + [0.0]                      # ρ_1 = 1, ρ_2 … ρ_m, ρ_{m+1} = 0
    out = []
    for k in range(1, m + 1):
        prod = math.prod(rho[:k])
        out.append(prod * (1.0 - rho[k]) * q / math.comb(m - 1, k - 1))
    return out


def alpha_q(q_total: float, alphas: Sequence[float], staggered: bool) -> list[float] | None:
    """Eq. 5.6 (escalonado) ou 5.7 (não escalonado): [Q_1, …, Q_m] com α_1…α_m = ``alphas`` (Σ α_k = 1)."""
    q = _prob(q_total)
    m = len(alphas) if isinstance(alphas, (list, tuple)) else 0
    a = _floats(list(alphas), m) if m >= 2 else None
    if q is None or a is None or abs(sum(a) - 1.0) > 1e-6:
        return None
    if staggered:
        return [a[k - 1] * q / math.comb(m - 1, k - 1) for k in range(1, m + 1)]
    a_t = sum(k * a[k - 1] for k in range(1, m + 1))           # Eq. 5.9
    return [k / math.comb(m - 1, k - 1) * a[k - 1] / a_t * q for k in range(1, m + 1)]


def mgl_to_alpha_staggered(greek: Sequence[float]) -> list[float]:
    """Tabela A-2 (escalonado): α_k = (Π_{i≤k} ρ_i)(1 − ρ_{k+1}), ρ_1 = 1, ρ_{m+1} = 0."""
    rho = [1.0] + [float(x) for x in greek] + [0.0]
    return [math.prod(rho[:k]) * (1.0 - rho[k]) for k in range(1, len(greek) + 2)]


def alpha_to_mgl_staggered(alphas: Sequence[float]) -> list[float]:
    """Tabela A-2 (escalonado): ρ_k = Σ_{j≥k} α_j / Σ_{j≥k−1} α_j (β = α_2 + … + α_m para Σ α = 1)."""
    a = [float(x) for x in alphas]
    tail = [sum(a[i:]) for i in range(len(a))]
    return [tail[k] / tail[k - 1] if tail[k - 1] > 0 else 0.0 for k in range(1, len(a))]


def apply_multi_ccf(tree: FaultTree, group_events: Sequence[str], qk: Sequence[float], *, group_id: str,
                    source: str, t_flight: float = 1.0) -> dict[str, Any]:
    """Modelo de parâmetros básicos na árvore: cada evento do grupo → OR(independente Q_1, CCF dos subconjuntos
    de ordem k ≥ 2 que o contêm, cada um com Q_k). Altera ``tree``. Q_t diferentes, m > M_MAX_FTA ou ids
    ocupados → árvore intacta e ``nao_avaliado``."""
    ids = list(dict.fromkeys(group_events))
    m = len(ids)
    out: dict[str, Any] = {"group": group_id, "events": ids, "method": source, "evaluated": False,
                           "veredicto": "nao_avaliado", "notes": []}
    if m < 2 or len(qk) != m:
        out["notes"].append("grupo com menos de dois eventos ou Q_k com tamanho diferente de m")
        return out
    if m > M_MAX_FTA:
        out["notes"].append(f"m = {m} > {M_MAX_FTA}: árvore com demasiados eventos CCF para avaliação exata")
        return out
    missing = [e for e in ids if e not in tree.events]
    if missing:
        out["notes"].append("eventos fora da árvore: " + ", ".join(missing))
        return out
    qs = [tree.events[e].q(t_flight) for e in ids]
    if max(qs) - min(qs) > _REL_EQUAL * max(max(qs), 1e-300):
        out["notes"].append("Q_t diferentes no grupo: o modelo é para componentes semelhantes")
        return out
    subsets = [c for k in range(2, m + 1) for c in combinations(range(m), k)]
    names = {c: f"{group_id}.CCF" + "".join(f".{i + 1}" for i in c) for c in subsets}
    if any(n in tree.events or n in tree.gates for n in names.values()):
        out["notes"].append("identificadores CCF já existem na árvore")
        return out
    for c, n in names.items():
        tree.add_event(BasicEvent(id=n, name=f"causa comum {group_id} ({len(c)} de {m})", prob=float(qk[len(c) - 1]),
                                  source=source))
    for i, e in enumerate(ids):
        old = tree.events.pop(e)
        ind = f"{e}.I"
        tree.add_event(BasicEvent(id=ind, name=(old.name or e) + " (independente)", prob=float(qk[0]),
                                  source=source, latent=old.latent))
        tree.add_gate(Gate(id=e, kind="OR", inputs=[ind] + [names[c] for c in subsets if i in c],
                           name=(old.name or e) + " (CCF)"))
    out.update({"evaluated": True, "veredicto": "validado", "Q_k": [float(x) for x in qk],
                "n_ccf_events": len(subsets)})
    return out


def _multi_group(raw: Mapping[str, Any], out: dict[str, Any], gid: str, q: float, m: int, k: int) -> dict[str, Any]:
    model = raw.get("model")
    src = raw.get("params_source")
    if model == "mgl":
        out["method"] = SOURCE_MGL
        greek = raw.get("mgl")
        qk = mgl_q(q, m, greek) if isinstance(greek, (list, tuple)) else None
        if qk is None or not isinstance(greek, (list, tuple)):
            out["notes"].append("mgl: lista [β, γ, δ, …] com m − 1 valores em [0, 1] em falta ou inválida")
            return out
        out["mgl"] = [float(x) for x in greek]
        out["alpha_escalonado"] = mgl_to_alpha_staggered(greek)
    else:
        out["method"] = SOURCE_ALPHA
        alphas, testing = raw.get("alpha"), raw.get("testing")
        if testing not in ("escalonado", "nao_escalonado"):
            out["notes"].append("testing (escalonado | nao_escalonado) em falta: o fator α depende do esquema de "
                                "ensaio (§5.3) e não tem omissão")
            return out
        qk = alpha_q(q, alphas, testing == "escalonado") if isinstance(alphas, (list, tuple)) and \
            len(alphas) == m else None
        if qk is None or not isinstance(alphas, (list, tuple)):
            out["notes"].append("alpha: lista [α_1, …, α_m] em [0, 1] com Σ α_k = 1 em falta ou inválida")
            return out
        out["alpha"], out["testing"] = [float(x) for x in alphas], testing
    if not src:
        out["notes"].append("params_source em falta: os parâmetros não se aplicam sem fonte declarada")
        out["q_top_bounds"] = {"lo": out["q_top_independent_only"], "hi": None}
        return out
    tree = redundancy_tree(gid, q, m, k)
    blk = apply_multi_ccf(tree, [f"{gid}.{i + 1}" for i in range(m)], qk, group_id=gid, source=out["method"])
    out["ccf_block"] = blk
    if not blk["evaluated"]:
        out["notes"] += blk["notes"]
        return out
    out["Q_k"] = qk
    out["sum_check_Q_t"] = sum(math.comb(m - 1, j - 1) * qk[j - 1] for j in range(1, m + 1))
    out["q_top"] = tree.top_probability()
    out["q_top_rare_event"] = tree.rare_event()
    out["minimal_cut_sets"] = [sorted(s) for s in tree.minimal_cut_sets()]
    out["params_source"] = str(src)
    out["model"] = model
    out["evaluated"], out["veredicto"] = True, "validado"
    return out
