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
Os modelos de mais parâmetros (MGL, fator α) não estão aqui.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from acdt.core.safety.fta import BasicEvent, FaultTree, Gate

SOURCE = ("NUREG/CR-5485 (Mosleh, Rasmuson e Marshall, NRC, nov. 1998) Apêndice A, Eq. A.10–A.13, p. A-5 "
          "(modelo do fator β de Fleming, 1975)")
_REL_EQUAL = 1e-9


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
            "nota": ("Valida a aplicação das Eq. A.10–A.13 com o β declarado; o valor de β vem da fonte declarada "
                     "pelo utilizador e não é verificado aqui. Não substitui o RBD ativo.")}
