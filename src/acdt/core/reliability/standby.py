# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Espera inativa (MIL-HDBK-338B §7.5.5.3) e Weibull de dois parâmetros (Eq. 5.50–5.51).

Só entram fórmulas lidas na página citada. O que a página não equaciona fica ``None`` e
``nao_avaliado`` — nunca zero e nunca um «passa».

Espera inativa, comutador perfeito (a Fig. 7.5-17 declara R_S = 1):

* dois elementos exponenciais, λ_a ≠ λ_b (p. 7-113):
  R(t) = [λ_b / (λ_b − λ_a)] e^{−λ_a t} − [λ_a / (λ_b − λ_a)] e^{−λ_b t};
  MTBF = (λ_a + λ_b) / (λ_a λ_b) = θ_a + θ_b;
* λ_a = λ_b torna a expressão singular; usa-se o caso de n elementos idênticos (p. 7-114 e a
  fórmula impressa na Fig. 7.5-17): R(t) = e^{−λ t} Σ_{r=0}^{n−1} (λ t)^r / r!, MTBF = n / λ;
* a p. 7-116 diz que a taxa dos comutadores tem de ser considerada a seguir e não dá equação.
  Taxa declarada não entra em R.

PRESSUPOSTO numérico: |λ_b − λ_a| ≤ 10^{−9} max(λ) trata-se como o limite de taxas iguais
(a expressão da p. 7-113 é singular na igualdade). PRESSUPOSTO do texto da secção: reserva
inativa (não energizada) até à comutação, sem reparação durante a missão. A Fig. 7.5-16
(p. 7-115) é votação por maioria e não entra aqui.

Weibull, γ = 0 (p. 5-23, Eq. 5.50 e 5.51, exemplo §5.3.6.1):
R(t) = exp[−(t/η)^β], h(t) = (β/η) (t/η)^{β−1}. γ ≠ 0 não foi transcrito. O MTTF por função
gama não está na página lida e não é calculado.

Causa comum: o §7.5.5.4 (p. 7-117) dá partilha de carga com fator k (θ′ = θ/k), não um fator β.
A partilha de carga não foi codificada. O fator β vem de NUREG/CR-5485 Ap. A (Eq. A.10–A.13), em
:mod:`.common_cause`, só com ``common_cause`` declarado.

Ligação ARP4761: um evento básico da FTA com q = 1 − R(t). Uma porta AND é a falha da
redundância ativa; uma porta OR é a falha em série. Nenhuma das duas é este modelo.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from acdt.core.safety.fta import BasicEvent, FaultTree

_REL_EQUAL = 1e-9
_N_MAX = 100_000
_SOURCE_STANDBY = (
    "MIL-HDBK-338B (1 out. 1998) §7.5.5.3, p. 7-113 (dois elementos), p. 7-114 (n idênticos) "
    "e Fig. 7.5-17 p. 7-116 (R_S = 1)"
)
_SOURCE_WEIBULL = "MIL-HDBK-338B (1 out. 1998) §5.3.6, Eq. 5.50 e 5.51, exemplo §5.3.6.1 (p. 5-23)"
_SOURCE_BETA = (
    "MIL-HDBK-338B §7.5.5.4 p. 7-117 descreve partilha de carga com fator k (θ′ = θ/k), "
    "não um fator β de causa comum. A equação λ_cc = β λ não está na página e não foi aplicada."
)
_FTA_SOURCE = (
    "q = 1 − R(t) da espera inativa com comutador perfeito (MIL-HDBK-338B §7.5.5.3, "
    "Fig. 7.5-17, R_S = 1). Uma porta OR ou AND dos elementos não é este modelo "
    "(ARP4761 / NUREG-0492, evento básico)."
)


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    v = float(x)
    return v if math.isfinite(v) else None


def _rate(x: Any) -> float | None:
    """Taxa [1/h]. Negativa ou não finita → ``None``. Zero é uma taxa declarada, não um desconhecido."""
    v = _num(x)
    if v is None or v < 0.0:
        return None
    return v


def _time(x: Any) -> float | None:
    v = _num(x)
    if v is None or v < 0.0:
        return None
    return v


def _count(n: Any) -> int | None:
    if isinstance(n, bool):
        return None
    if isinstance(n, int):
        k = n
    elif isinstance(n, float) and n.is_integer():
        k = int(n)
    else:
        return None
    if k < 1 or k > _N_MAX:
        return None
    return k


def _unit(x: float) -> float | None:
    if not math.isfinite(x):
        return None
    if -1e-12 <= x < 0.0:
        return 0.0
    if 1.0 < x <= 1.0 + 1e-12:
        return 1.0
    if 0.0 <= x <= 1.0:
        return x
    return None


def _poisson_reliability(x: float, n: int) -> float | None:
    """e^{−x} Σ_{r=0}^{n−1} x^r / r! (soma impressa na Fig. 7.5-17)."""
    if x == 0.0:
        return 1.0
    if x < 0.0 or n < 1:
        return None
    log_term = -x
    m = log_term
    logs = [log_term]
    for r in range(1, n):
        log_term += math.log(x) - math.log(r)
        logs.append(log_term)
        if log_term > m:
            m = log_term
    if m < -700.0:
        return 0.0
    s = math.exp(m) * sum(math.exp(v - m) for v in logs)
    return _unit(s)


def inactive_standby_reliability(lam_per_h: float, n: int, t_h: float) -> float | None:
    """R(t) de n elementos idênticos em espera inativa, comutador perfeito (p. 7-114, Fig. 7.5-17).

    n é o total de elementos (o que opera e os que esperam): n = 1 é a exponencial. λ = 0 (declarado)
    dá R = 1. Entrada inválida → ``None``.
    """
    lam = _rate(lam_per_h)
    k = _count(n)
    t = _time(t_h)
    if lam is None or k is None or t is None:
        return None
    if lam == 0.0:
        return 1.0
    return _poisson_reliability(lam * t, k)


def inactive_standby_mtbf_h(lam_per_h: float, n: int) -> float | None:
    """MTBF = n / λ (p. 7-114). λ = 0 → infinito, devolvido como ``None`` (não como zero)."""
    lam = _rate(lam_per_h)
    k = _count(n)
    if lam is None or k is None or lam == 0.0:
        return None
    return k / lam


def _rates_equal(lam_a: float, lam_b: float) -> bool:
    scale = max(lam_a, lam_b, 0.0)
    if scale == 0.0:
        return True
    return abs(lam_b - lam_a) <= _REL_EQUAL * scale


def inactive_standby_reliability_two(lam_a_per_h: float, lam_b_per_h: float, t_h: float) -> float | None:
    """R(t) de dois elementos exponenciais (p. 7-113). Taxas iguais: caso n = 2 da p. 7-114."""
    la = _rate(lam_a_per_h)
    lb = _rate(lam_b_per_h)
    t = _time(t_h)
    if la is None or lb is None or t is None:
        return None
    if la == 0.0 or lb == 0.0:
        # Limite da fórmula da p. 7-113: um elemento que não avaria dá R = 1.
        return 1.0
    if _rates_equal(la, lb):
        return _poisson_reliability(0.5 * (la + lb) * t, 2)
    d = lb - la
    r = (lb / d) * math.exp(-la * t) - (la / d) * math.exp(-lb * t)
    return _unit(r)


def inactive_standby_mtbf_two_h(lam_a_per_h: float, lam_b_per_h: float) -> float | None:
    """MTBF = θ_a + θ_b (p. 7-113). Alguma taxa nula → MTBF infinita → ``None``."""
    la = _rate(lam_a_per_h)
    lb = _rate(lam_b_per_h)
    if la is None or lb is None or la == 0.0 or lb == 0.0:
        return None
    return (la + lb) / (la * lb)


def switching_status(switch_rate_per_h: float | None) -> dict[str, Any]:
    """A Fig. 7.5-17 fixa R_S = 1. A p. 7-116 não dá a taxa do comutador.

    Sem taxa declarada, o R transcrito assume o comutador perfeito. Com taxa declarada, essa taxa
    não é aplicada e o R pedido fica por avaliar (não se substitui a taxa por zero).
    """
    declared = switch_rate_per_h is not None
    rate = _rate(switch_rate_per_h) if declared else None
    bad = declared and rate is None
    return {
        "model": "perfeito" if not declared else "imperfeito_nao_transcrito",
        "R_S": 1.0 if not declared else None,
        "applied_perfect_switch": not declared and not bad,
        "declared_rate_per_h": None if not declared else switch_rate_per_h,
        "imperfect": {
            "evaluated": False,
            "veredicto": "nao_avaliado",
            "applied": False,
            "rate_per_h": None if bad else rate,
            "note": (
                "A Fig. 7.5-17 declara R_S = 1. A p. 7-116 diz que a taxa dos dispositivos de "
                "comutação tem de ser considerada e não dá equação. A taxa declarada não entra em R."
            ),
        },
    }


def common_cause_status() -> dict[str, Any]:
    """Sem ``common_cause`` declarado: o fator β não entra (o §7.5.5.4 do MIL-HDBK-338B não o dá)."""
    return {
        "evaluated": False,
        "veredicto": "nao_avaliado",
        "calibracao": "nao_aplicar",
        "beta": None,
        "method": None,
        "source": _SOURCE_BETA,
        "available": ("common_cause: {groups: [{id, m, k_fail, q_total | lambda_per_h + t_h, beta, beta_source}]} "
                      "— NUREG/CR-5485 Ap. A, Eq. A.10–A.13 (acdt.core.reliability.common_cause)"),
    }


def weibull_reliability(t_h: float, shape: float, scale_h: float,
                        location_h: float | None = None) -> float | None:
    """R(t) da Eq. 5.50 (γ = 0). γ ≠ 0 → ``None`` (não transcrito)."""
    if location_h is not None and location_h != 0.0:
        return None
    t = _time(t_h)
    beta = _rate(shape)
    eta = _rate(scale_h)
    if t is None or beta is None or eta is None or beta == 0.0 or eta == 0.0:
        return None
    if t == 0.0:
        return 1.0
    return _unit(math.exp(-((t / eta) ** beta)))


def weibull_hazard_per_h(t_h: float, shape: float, scale_h: float,
                         location_h: float | None = None) -> float | None:
    """h(t) da Eq. 5.51. Em t = 0 e β < 1 a expressão é singular: ``None``, não zero."""
    if location_h is not None and location_h != 0.0:
        return None
    t = _time(t_h)
    beta = _rate(shape)
    eta = _rate(scale_h)
    if t is None or beta is None or eta is None or beta == 0.0 or eta == 0.0:
        return None
    if t == 0.0:
        if beta > 1.0:
            return 0.0
        if beta == 1.0:
            return 1.0 / eta
        return None
    h = (beta / eta) * (t / eta) ** (beta - 1.0)
    return h if math.isfinite(h) and h >= 0.0 else None


def standby_fault_event(event_id: str, reliability: float, *, name: str = "") -> BasicEvent | None:
    """Evento básico com q = 1 − R. R inválido → ``None`` (não se cria um q fictício)."""
    r = _unit(reliability) if isinstance(reliability, (int, float)) and not isinstance(reliability, bool) else None
    if r is None:
        return None
    return BasicEvent(id=event_id, name=name or "espera inativa", prob=1.0 - r, source=_FTA_SOURCE)


def standby_fault_tree(event_id: str, reliability: float, *, name: str = "") -> FaultTree | None:
    """Árvore cujo topo é o evento de espera. O corte mínimo é esse evento, não os elementos."""
    ev = standby_fault_event(event_id, reliability, name=name)
    if ev is None:
        return None
    tree = FaultTree(top=ev.id, name=name or "espera inativa §7.5.5.3")
    tree.add_event(ev)
    return tree


def _standby_block(block: Any, mission_h: float | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "evaluated": False,
        "veredicto": "nao_avaliado",
        "calibracao": "nao_aplicar",
        "replaces_rbd": False,
        "R": None,
        "mtbf_h": None,
        "method": _SOURCE_STANDBY,
        "switch": switching_status(None),
        "fta": {"model": None, "q": None, "gate_expansion": "nao_aplicado",
                "note": _FTA_SOURCE},
        "notes": [],
    }
    if not isinstance(block, Mapping):
        out["notes"].append("standby não é um mapa: não avaliado")
        return out
    sw_raw = block.get("switch_rate_per_h", None)
    declared_switch = "switch_rate_per_h" in block and sw_raw is not None
    out["switch"] = switching_status(sw_raw if declared_switch else None)
    has_pair = "lambda_a_per_h" in block or "lambda_b_per_h" in block
    has_ident = "lambda_per_h" in block or "n" in block
    if has_pair and has_ident:
        out["notes"].append("formas λ e (λ_a, λ_b) em simultâneo: não se escolhe uma")
        return out
    t_raw = block.get("t_h", mission_h)
    if has_pair:
        if block.get("n") not in (None, 2, 2.0):
            out["notes"].append("dois elementos pedem n = 2")
            return out
        la, lb = block.get("lambda_a_per_h"), block.get("lambda_b_per_h")
        if _rate(la) is None or _rate(lb) is None:
            out["notes"].append("λ_a ou λ_b em falta ou inválida")
            return out
        assert la is not None and lb is not None
        out["mtbf_h"] = inactive_standby_mtbf_two_h(float(la), float(lb))
        if _time(t_raw) is None:
            out["notes"].append("duração em falta: R desconhecido")
            return out
        out["R"] = inactive_standby_reliability_two(float(la), float(lb), float(t_raw))
        out["form"] = "dois_elementos"
    else:
        lam, n = block.get("lambda_per_h"), block.get("n")
        k = _count(n)
        if _rate(lam) is None or k is None:
            out["notes"].append("λ ou n em falta ou inválido")
            return out
        assert lam is not None
        out["mtbf_h"] = inactive_standby_mtbf_h(float(lam), k)
        if _time(t_raw) is None:
            out["notes"].append("duração em falta: R desconhecido")
            return out
        out["R"] = inactive_standby_reliability(float(lam), k, float(t_raw))
        out["form"] = "identicos"
    if out["R"] is None:
        out["notes"].append("R não calculado")
        return out
    if declared_switch:
        out["R_perfect_switch"] = out["R"]
        out["R"] = None
        out["notes"].append("taxa de comutador declarada: o R com R_S = 1 fica em R_perfect_switch e não é o resultado")
        return out
    out["evaluated"] = True
    out["veredicto"] = "validado"
    out["fta"] = {
        "model": "evento_basico",
        "q": 1.0 - float(out["R"]),
        "gate_expansion": "nao_aplicado",
        "note": _FTA_SOURCE,
    }
    return out


def _weibull_item(item: Mapping[str, Any], mission_h: float | None) -> dict[str, Any]:
    loc = item.get("location_h", None)
    row: dict[str, Any] = {
        "id": item.get("id"),
        "evaluated": False,
        "veredicto": "nao_avaliado",
        "R": None,
        "hazard_per_h": None,
        "method": _SOURCE_WEIBULL if loc in (None, 0, 0.0) else None,
        "notes": [],
    }
    if loc not in (None, 0, 0.0):
        row["notes"].append("γ ≠ 0 não transcrito (a Eq. 5.50 é o caso γ = 0)")
        return row
    t_raw = item.get("t_h", mission_h)
    if _time(t_raw) is None or _rate(item.get("shape")) is None or _rate(item.get("scale_h")) is None:
        row["notes"].append("t, β ou η em falta ou inválido")
        return row
    assert t_raw is not None
    shape = float(item["shape"])
    scale = float(item["scale_h"])
    t = float(t_raw)
    row["R"] = weibull_reliability(t, shape, scale, 0.0)
    row["hazard_per_h"] = weibull_hazard_per_h(t, shape, scale, 0.0)
    if row["R"] is None or row["hazard_per_h"] is None:
        row["notes"].append("R ou h não calculado (singular ou entrada inválida)")
        return row
    row["evaluated"] = True
    row["veredicto"] = "validado"
    return row


def _weibull_block(raw: Any, mission_h: float | None) -> dict[str, Any]:
    if not isinstance(raw, list) or not raw:
        return {"evaluated": False, "veredicto": "nao_avaliado", "items": [],
                "method": _SOURCE_WEIBULL, "notes": ["weibull sem lista de itens"]}
    items = []
    for it in raw:
        if isinstance(it, Mapping):
            items.append(_weibull_item(it, mission_h))
        else:
            items.append({"id": None, "evaluated": False, "veredicto": "nao_avaliado", "R": None,
                          "hazard_per_h": None, "notes": ["item inválido"]})
    ok = all(bool(i.get("evaluated")) for i in items)
    return {"evaluated": ok, "veredicto": "validado" if ok else "nao_avaliado", "items": items,
            "method": _SOURCE_WEIBULL, "notes": [], "calibracao": "nao_aplicar"}


def evaluate_extensions(spec: Mapping[str, Any], mission_h: float | None) -> dict[str, Any]:
    """Bloco lateral. Não altera o RBD ativo. Ausente o que não foi pedido (``nao_pedido``)."""
    standby = _standby_block(spec["standby"], mission_h) if "standby" in spec else {
        "veredicto": "nao_pedido", "evaluated": False, "R": None, "replaces_rbd": False}
    weibull = _weibull_block(spec["weibull"], mission_h) if "weibull" in spec else {
        "veredicto": "nao_pedido", "evaluated": False, "items": []}
    from .common_cause import common_cause_block

    ccf = common_cause_block(spec.get("common_cause"), mission_h) if "common_cause" in spec else None
    asked = [b for b in (standby, weibull) if b.get("veredicto") != "nao_pedido"]
    if ccf is not None:
        asked.append(ccf)
    ok = bool(asked) and all(b.get("veredicto") == "validado" for b in asked)
    return {
        "veredicto": "validado" if ok else "nao_avaliado",
        "calibracao": "nao_aplicar",
        "nota_veredicto": (
            "Válido só para as identidades transcritas (espera com R_S = 1 e Weibull com γ = 0). "
            "O comutador imperfeito e γ ≠ 0 ficam nao_avaliado. O fator β só entra com common_cause "
            "declarado (NUREG/CR-5485 Eq. A.10–A.13, β e a sua fonte dados pelo utilizador)."
        ),
        "standby": standby,
        "weibull": weibull,
        "common_cause": ccf if ccf is not None else common_cause_status(),
        "comutador_imperfeito": "nao_avaliado",
        "fator_beta": ccf["veredicto"] if ccf is not None else "nao_avaliado",
        "weibull_gama_nao_nulo": "nao_avaliado",
        "replaces_rbd": False,
    }
