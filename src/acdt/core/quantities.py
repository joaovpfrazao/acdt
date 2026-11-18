# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Grandezas com unidades na fronteira de entrada/saída (pint), sem tocar no núcleo numérico.

O núcleo do acdt continua a trabalhar em números simples: SI nos requisitos (:mod:`acdt.core.units`) e, nas
``assumptions``, na unidade que **o nome da chave declara** (``fuselage_length_m`` → m, ``arm_in`` → in,
``engine_kW_per_kg`` → kW/kg). Este módulo só converte à entrada:

* número simples → fica como está (compatibilidade: os YAML antigos sem unidades continuam iguais, SI/unidade
  da chave assumida, como sempre);
* texto ``"150 kg"``, ``"27 m/s"``, ``"10 h"`` ou mapa ``{value: 150, unit: kg}`` → convertido para a unidade
  interna; dimensão errada (``"3 kg"`` numa chave ``_m``) → :class:`QuantityError` com o caminho, a dimensão
  recebida e a esperada.

A unidade dos resultados (``result.json``) lê-se pela mesma convenção de sufixo (:func:`unit_from_key`);
chaves sem sufixo reconhecido ficam com unidade **não declarada** (``None``), nunca «adimensional» por omissão.

pint (BSD-3-Clause) é carregado só quando aparece uma unidade escrita em texto que a tabela exata de
:mod:`acdt.core.units` (NIST SP 811, 2008, Apêndice B) não cobre; com a tabela, o fator é o mesmo de sempre.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from acdt.core import units

__all__ = ["QuantityError", "parse_quantity", "to_unit", "to_dimension_si", "unit_from_key", "normalise_tree",
           "convert", "same_dimension", "DIMENSION_SI", "SUFFIX_UNITS"]


class QuantityError(units.UnitError):
    """Entrada com unidade inválida ou dimensionalmente errada (subclasse de ValueError)."""


# Unidade SI (sintaxe pint) de cada dimensão de acdt.core.units. As dimensões sem equivalente físico (moeda,
# dB, categoria, constante de rotação) só aceitam as unidades da tabela própria.
DIMENSION_SI: dict[str, str] = {
    "length": "m", "time": "s", "mass": "kg", "speed": "m/s", "power": "W", "energy": "J", "force": "N",
    "angle": "rad", "angular_rate": "rad/s", "area": "m**2", "wing_loading": "Pa", "dimensionless": "",
    "voltage": "V", "current": "A", "specific_energy": "J/kg", "torque": "N*m", "stress": "Pa",
    "density": "kg/m**3", "strain": "", "electric_charge": "C",
}

# Sufixo da chave → unidade (sintaxe pint). Procura do sufixo mais longo para o mais curto. ``_g`` (fator de
# carga) e ``_s`` ambíguo não entram em dúvida: ``_g`` fica de fora (seria grama), ``_s`` é segundo.
SUFFIX_UNITS: dict[str, str] = {
    "kg": "kg", "g_mass": "g", "lb": "lb", "t": "t",
    "m": "m", "mm": "mm", "cm": "cm", "km": "km", "ft": "ft", "in": "inch", "nmi": "nmi",
    "m2": "m**2", "mm2": "mm**2", "cm2": "cm**2", "ft2": "ft**2", "m3": "m**3", "L": "L",
    "m4": "m**4", "mm4": "mm**4",
    "s": "s", "ms": "ms", "min": "min", "h": "h",
    "m_s": "m/s", "km_h": "km/h", "kt": "knot", "kts": "knot", "ft_s": "ft/s", "ft_min": "ft/min",
    "m_s2": "m/s**2",
    "deg": "deg", "rad": "rad", "deg_s": "deg/s", "rad_s": "rad/s", "per_rad": "1/rad", "per_deg": "1/deg",
    "rpm": "rpm", "Hz": "Hz",
    "W": "W", "kW": "kW", "MW": "MW", "hp": "hp", "J": "J", "kJ": "kJ", "MJ": "MJ", "Wh": "W*h", "kWh": "kW*h",
    "N": "N", "kN": "kN", "lbf": "lbf", "Nm": "N*m", "N_m": "N*m", "Nmm": "N*mm",
    "Pa": "Pa", "kPa": "kPa", "MPa": "MPa", "GPa": "GPa", "N_m2": "N/m**2", "psf": "lbf/ft**2", "psi": "psi",
    "kg_m2": "kg/m**2", "kg_m3": "kg/m**3", "kgm2": "kg*m**2", "kg_m": "kg/m", "N_m_rad": "N*m/rad",
    "Nm2": "N*m**2", "Nm_rad": "N*m/rad",
    "K": "K", "V": "V", "A": "A", "Ah": "A*h", "mAh": "mA*h", "Ohm": "ohm", "ohm": "ohm",
    "W_kg": "W/kg", "kW_kg": "kW/kg", "Wh_kg": "W*h/kg", "J_kg": "J/kg", "N_kW": "N/kW",
    "kg_s": "kg/s", "kg_h": "kg/h", "g_kWh": "g/(kW*h)", "kg_kWh": "kg/(kW*h)", "kg_Nh": "kg/(N*h)",
    "dB": "dB_acdt", "dBsm": "dBsm_acdt", "USD": "USD_acdt", "kUSD": "kUSD_acdt",
    "percent": "percent", "pct": "percent", "ratio": "1", "fraction": "1",
}
_SUFFIX_KEYS = sorted(SUFFIX_UNITS, key=len, reverse=True)
# unidades não-físicas: comparadas por igualdade de texto, nunca convertidas por pint
_OPAQUE = {"dB_acdt": "dB", "dBsm_acdt": "dBsm", "USD_acdt": "USD", "kUSD_acdt": "kUSD"}

_NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_QTY_RE = re.compile(rf"^\s*({_NUM})\s*([^\d\s].*?)?\s*$")


@lru_cache(maxsize=1)
def ureg() -> Any:
    """Registo pint partilhado (carregamento preguiçoso) com os aliases de aviação de acdt.core.units."""
    try:
        import pint
    except ImportError as e:  # pragma: no cover — pint é dependência declarada
        raise QuantityError("unidades em texto precisam do pacote 'pint' (pip install pint)") from e
    r = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)
    for line in ("KTAS = knot", "kts = knot", "fpm = foot / minute", "shp = horsepower", "NM = nautical_mile",
                 "Nm = newton * meter", "m2 = meter ** 2", "ft2 = foot ** 2", "kg_m2 = kilogram / meter ** 2",
                 "mi = mile"):
        try:
            r.define(line)
        except Exception:  # noqa: BLE001 — já definido nesta versão do pint
            pass
    return r


def parse_quantity(text: str) -> tuple[float, str]:
    """``"150 kg"`` → ``(150.0, "kg")``; ``"27"`` → ``(27.0, "")``. Erro se não for número + unidade."""
    m = _QTY_RE.match(str(text))
    if not m:
        raise QuantityError(f"'{text}' não é uma grandeza (esperado número seguido de unidade, p. ex. '150 kg')")
    return float(m.group(1)), (m.group(2) or "").strip()


def looks_like_quantity(text: Any) -> bool:
    return isinstance(text, str) and bool(_QTY_RE.match(text)) and bool(_QTY_RE.match(text).group(2))  # type: ignore[union-attr]


def _split(value: Any, where: str) -> tuple[float, str | None]:
    """Número simples → (v, None); texto/mapa com unidade → (v, unidade)."""
    if isinstance(value, bool):
        raise QuantityError(f"{where}: booleano não é uma grandeza")
    if isinstance(value, (int, float)):
        return float(value), None
    if isinstance(value, dict) and "value" in value:
        v = value["value"]
        if isinstance(v, str):
            mag, u = parse_quantity(v)
            return mag, (u or value.get("unit"))
        return float(v), value.get("unit")
    if isinstance(value, str):
        mag, u = parse_quantity(value)
        return mag, (u or None)
    raise QuantityError(f"{where}: valor {value!r} não é número nem grandeza com unidade")


def _dim_text(q: Any) -> str:
    d = str(q.dimensionality)
    return d if d != "dimensionless" else "adimensional"


def convert(value: float, unit: str, target: str, where: str = "") -> float:
    """Converte ``value`` de ``unit`` para ``target`` (sintaxe pint). Dimensão diferente → QuantityError."""
    pre = f"{where}: " if where else ""
    if unit == target:
        return float(value)
    if unit in _OPAQUE or target in _OPAQUE or unit in _OPAQUE.values() or target in _OPAQUE.values():
        raise QuantityError(f"{pre}não há conversão entre '{unit}' e '{target}' (unidade não física)")
    r = ureg()
    try:
        q = r.Quantity(float(value), unit or "dimensionless")
    except Exception as e:  # noqa: BLE001
        raise QuantityError(f"{pre}unidade '{unit}' desconhecida ({e})") from e
    try:
        tq = r.Quantity(1.0, target or "dimensionless")
    except Exception as e:  # noqa: BLE001
        raise QuantityError(f"{pre}unidade interna '{target}' desconhecida ({e})") from e
    if q.dimensionality != tq.dimensionality:
        raise QuantityError(f"{pre}'{value} {unit}' tem dimensão {_dim_text(q)}, mas é esperado {_dim_text(tq)} "
                            f"(unidade interna '{target or '1'}')")
    return float(q.to(tq.units).magnitude)


def same_dimension(u1: str | None, u2: str | None) -> bool:
    if u1 is None or u2 is None:
        return u1 == u2
    if u1 == u2:
        return True
    try:
        r = ureg()
        return bool(r.Quantity(1.0, u1 or "dimensionless").dimensionality ==
                    r.Quantity(1.0, u2 or "dimensionless").dimensionality)
    except Exception:  # noqa: BLE001
        return False


def to_unit(value: Any, target: str, where: str = "") -> float:
    """Valor de entrada → número na unidade interna ``target``. Número simples: já está em ``target``."""
    mag, u = _split(value, where)
    if u is None:
        return mag
    return convert(mag, u, target, where)


def to_dimension_si(value: Any, dimension: str, where: str = "") -> tuple[float, float, str]:
    """Para os requisitos (dimensões de acdt.core.units). Devolve ``(valor_SI, valor_escrito, unidade_escrita)``.

    Unidade da tabela exata de acdt.core.units → o fator de sempre; outra unidade → pint para o SI da dimensão.
    """
    mag, u = _split(value, where)
    if u is None:
        u = units.default_unit(dimension)
    table = units._UNITS.get(dimension)
    if table is None:
        raise QuantityError(f"{where}: dimensão '{dimension}' desconhecida")
    if u in table:
        return units.to_si(mag, u, dimension), mag, u
    si = DIMENSION_SI.get(dimension)
    if si is None:
        raise QuantityError(f"{where}: unidade '{u}' não válida para {dimension}; use uma de {sorted(table)}")
    return convert(mag, u, si, where), mag, u


def unit_from_key(key: str) -> str | None:
    """Unidade declarada pelo sufixo do nome da chave (``W0_kg`` → ``kg``; ``CD0`` → None = não declarada)."""
    k = str(key)
    if "_per_" in k:
        num, den = k.rsplit("_per_", 1)
        un, ud = unit_from_key(num), SUFFIX_UNITS.get(den)
        if un is not None and ud is not None and un not in _OPAQUE and ud not in _OPAQUE:
            return f"{un}/({ud})" if un != "1" else f"1/({ud})"
        if un is None and ud is not None and den in ("rad", "deg"):
            return SUFFIX_UNITS[f"per_{den}"]
        return None
    for s in _SUFFIX_KEYS:
        if k.endswith("_" + s) and len(k) > len(s) + 1:
            return SUFFIX_UNITS[s]
    return None


def display_unit(u: str | None) -> str:
    if u is None:
        return ""
    return _OPAQUE.get(u, u)


def normalise_tree(obj: Any, where: str = "") -> Any:
    """Converte, numa árvore YAML (assumptions, systems…), os valores com unidade escrita para a unidade que a
    chave declara. Devolve uma cópia; números simples e textos que não são grandezas ficam iguais.

    Erros (com o caminho): dimensão errada; grandeza com unidade numa chave sem unidade declarada (não se adivinha
    em que unidade o núcleo a espera).
    """
    if isinstance(obj, dict):
        return {k: _norm_value(k, v, f"{where}.{k}" if where else str(k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalise_tree(x, f"{where}[{i}]") for i, x in enumerate(obj)]
    return obj


def _norm_value(key: Any, v: Any, where: str) -> Any:
    target = unit_from_key(str(key))
    if isinstance(v, dict):
        if target is not None and "value" in v and set(v) <= {"value", "unit"}:
            return to_unit(v, target, where)
        return normalise_tree(v, where)
    if isinstance(v, list):
        if target is not None:
            return [_norm_value(key, x, f"{where}[{i}]") for i, x in enumerate(v)]
        return normalise_tree(v, where)
    if looks_like_quantity(v):
        if target is None:
            raise QuantityError(f"{where}: '{v}' tem unidade, mas a chave '{key}' não declara a unidade interna "
                                f"(sufixo como _m, _kg, _deg); escreva o número na unidade que o modelo usa")
        if target in _OPAQUE:
            mag, u = parse_quantity(v)
            if u not in (_OPAQUE[target], target):
                raise QuantityError(f"{where}: unidade '{u}' não convertível para '{_OPAQUE[target]}'")
            return mag
        return to_unit(v, target, where)
    return v
