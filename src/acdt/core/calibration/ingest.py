# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ingestão de dados medidos (``acdt.testdata/1``), domínio-agnóstica.

Um conjunto de dados (:class:`Dataset`) é uma tabela de canais com **unidade explícita** (sintaxe pint,
:mod:`acdt.core.quantities`; ``None`` = unidade não declarada, nunca «adimensional» por omissão), metadados
(origem, data, condições do ensaio, instrumento) e a incerteza de instrumento por canal quando é conhecida
(desconhecida ≠ zero: sem declaração o campo não existe). O ficheiro de origem fica identificado pelo SHA-256
(:func:`acdt.core.provenance.hash_input`).

Formatos:

* **CSV** (biblioteca padrão): cabeçalho ``alpha [deg]``, ``alpha (deg)`` ou sufixo de unidade da convenção do acdt
  (``V_m_s``, ``alpha_deg``); linhas começadas por ``#`` são comentários; células vazias → ``NaN`` (em falta);
* **Parquet** (pandas + pyarrow, Apache-2.0, opcional): unidades pelo nome da coluna ou pelos metadados;
* **PX4 ULog** (pyulog, BSD-3-Clause, opcional, no processo): canais ``tópico.campo``; o campo ``timestamp`` do
  PX4 é em microssegundos (documentação uORB do PX4); os restantes pelo sufixo do nome (``_m_s``) ou ficam com
  unidade não declarada, salvo declaração nos metadados. **ArduPilot .bin** não é lido aqui: o leitor de referência (pymavlink) é LGPL-3.0;
  converte-se fora do processo (``mavlogdump.py --format csv``) e ingere-se o CSV.

Metadados: ficheiro ``<dados>.meta.yaml`` ao lado dos dados ou mapa passado a :func:`load`. Campos:
``source`` (obrigatório: relatório de ensaio, publicação com citação ou ``synthetic: true`` declarado),
``date``, ``kind`` (:data:`KINDS`), ``conditions`` (mapa; grandezas com unidade em texto aceites),
``instrument`` (texto), ``license``, ``synthetic`` e ``channels: {nome: {unit, uncertainty, rename}}``.
Incerteza por canal (GUM, JCGM 100:2008): ``{sd: …}`` (incerteza-padrão, tipo A ou B), ``{half_width: a}``
(distribuição retangular, u = a/√3, GUM 4.3.7) ou ``{resolution: δ}`` (resolução de leitura, u = δ/(2√3),
GUM F.2.2.1), todas na unidade do canal, ou ``{rel: r}`` (u = r·|valor|).
"""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import numpy.typing as npt

Array = npt.NDArray[np.float64]

SCHEMA = "acdt.testdata/1"
KINDS = ("tunel", "voo", "estatico", "bancada", "publicado", "outro")
FORMATS = ("csv", "parquet", "ulog")
GUM = "JCGM 100:2008 (GUM), 4.3.7 e F.2.2.1"
_HDR_UNIT = re.compile(r"^\s*(.+?)\s*[\[(]\s*([^\])]*)\s*[\])]\s*$")


class IngestError(ValueError):
    pass


@dataclass
class Channel:
    """Um canal medido: valores (NaN = em falta), unidade (``None`` = não declarada) e incerteza-padrão."""

    name: str
    values: Array
    unit: str | None
    uncertainty: dict[str, Any] | None = None  # {kind, sd | rel, source}; sd na unidade do canal

    def sd(self) -> Array | None:
        """Incerteza-padrão por ponto (na unidade do canal) ou ``None`` se desconhecida."""
        u = self.uncertainty
        if not u:
            return None
        if "sd" in u:
            return np.full(self.values.shape, float(u["sd"]))
        if "rel" in u:
            return np.abs(self.values) * float(u["rel"])
        return None

    def to(self, unit: str) -> Array:
        """Valores convertidos para ``unit`` (conversões afins, p. ex. °C → K, incluídas)."""
        return np.asarray(_affine(self.unit, unit, self.name)(self.values), dtype=float)

    def sd_to(self, unit: str) -> Array | None:
        s = self.sd()
        if s is None:
            return None
        f = _affine(self.unit, unit, self.name)
        return np.asarray(np.abs(f(s) - f(np.zeros_like(s))), dtype=float)  # só a escala (o desvio da origem cancela)

    def summary(self) -> dict[str, Any]:
        v = self.values[np.isfinite(self.values)]
        return {"unit": self.unit, "n": int(v.size), "n_missing": int(self.values.size - v.size),
                "min": float(np.min(v)) if v.size else None, "max": float(np.max(v)) if v.size else None,
                "uncertainty": self.uncertainty}


def _affine(unit: str | None, target: str, where: str) -> Any:
    from acdt.core.quantities import QuantityError, convert

    if unit is None:
        raise IngestError(f"canal '{where}': unidade não declarada; não converto para '{target}' (declare a unidade "
                          f"nos metadados)")
    if unit == target:
        return lambda x: np.asarray(x, dtype=float)
    try:
        a0 = convert(0.0, unit, target, where)
        a1 = convert(1.0, unit, target, where)
    except QuantityError as e:
        raise IngestError(str(e)) from e
    return lambda x: a0 + (a1 - a0) * np.asarray(x, dtype=float)


def standard_uncertainty(spec: Mapping[str, Any] | None, where: str) -> dict[str, Any] | None:
    """Normaliza a declaração de incerteza de um canal para ``{kind, sd|rel, source}`` (GUM)."""
    if not spec:
        return None
    s = dict(spec)
    src = str(s.get("source") or "")
    if not src:
        raise IngestError(f"{where}: incerteza sem 'source' (calibração do instrumento, ficha técnica ou PRESSUPOSTO)")
    if "sd" in s:
        sd = float(s["sd"])
        how = "incerteza-padrão declarada"
    elif "half_width" in s:
        sd, how = float(s["half_width"]) / math.sqrt(3.0), "retangular ±a → a/√3 (GUM 4.3.7)"
    elif "resolution" in s:
        sd, how = float(s["resolution"]) / (2.0 * math.sqrt(3.0)), "resolução δ → δ/(2√3) (GUM F.2.2.1)"
    elif "rel" in s:
        r = float(s["rel"])
        if not (math.isfinite(r) and r >= 0):
            raise IngestError(f"{where}: incerteza relativa inválida {r}")
        return {"kind": "relativa", "rel": r, "how": "relativa declarada", "source": src}
    else:
        raise IngestError(f"{where}: incerteza sem sd / half_width / resolution / rel")
    if not (math.isfinite(sd) and sd >= 0):
        raise IngestError(f"{where}: incerteza inválida {sd}")
    return {"kind": "desvio_padrao", "sd": sd, "how": how, "source": src}


@dataclass
class Dataset:
    name: str
    channels: dict[str, Channel]
    meta: dict[str, Any] = field(default_factory=dict)
    file: dict[str, Any] | None = None  # {path, sha256, size_bytes} (acdt.core.provenance.hash_input)
    fmt: str = ""

    @property
    def synthetic(self) -> bool:
        return bool(self.meta.get("synthetic"))

    @property
    def n(self) -> int:
        return max((c.values.size for c in self.channels.values()), default=0)

    def channel(self, name: str) -> Channel:
        if name not in self.channels:
            raise IngestError(f"{self.name}: canal '{name}' não existe (canais: {sorted(self.channels)})")
        return self.channels[name]

    def subset(self, mask: Array) -> "Dataset":
        m = np.asarray(mask, dtype=bool)
        return Dataset(self.name, {k: Channel(c.name, c.values[m], c.unit, c.uncertainty)
                                   for k, c in self.channels.items()}, dict(self.meta), self.file, self.fmt)

    def where(self, **eq: float) -> "Dataset":
        """Linhas em que cada canal é igual ao valor dado (na unidade do canal), p. ex. ``where(flap_deg=0)``."""
        m = np.ones(self.n, dtype=bool)
        for k, v in eq.items():
            m &= np.isclose(self.channel(k).values, float(v))
        return self.subset(m)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "name": self.name, "format": self.fmt, "file": self.file, "n_rows": self.n,
                "synthetic": self.synthetic, "meta": self.meta,
                "channels": {k: c.summary() for k, c in self.channels.items()}}


# ------------------------------------------------------------------------------------------------ metadados
def _check_meta(meta: Mapping[str, Any], where: str) -> dict[str, Any]:
    from acdt.core.quantities import normalise_tree

    m = dict(meta or {})
    if not m.get("source") and not m.get("synthetic"):
        raise IngestError(f"{where}: metadados sem 'source' (relatório de ensaio ou publicação). Dados sintéticos "
                          f"têm de vir marcados 'synthetic: true' com 'source' a dizer como foram gerados")
    if m.get("synthetic") and not m.get("source"):
        raise IngestError(f"{where}: dados sintéticos sem 'source' (como foram gerados: modelo, parâmetros, semente)")
    kind = m.get("kind", "outro")
    if kind not in KINDS:
        raise IngestError(f"{where}: kind '{kind}' não é um de {KINDS}")
    m["kind"] = kind
    m.setdefault("date", None)  # desconhecida ≠ hoje
    m["conditions"] = normalise_tree(dict(m.get("conditions") or {}), "conditions")
    return m


def meta_path(data: str | Path) -> Path:
    p = Path(data)
    return p.with_name(p.name + ".meta.yaml")


def _read_meta(data: Path, meta: Mapping[str, Any] | str | Path | None) -> dict[str, Any]:
    import yaml

    if isinstance(meta, (str, Path)):
        return dict(yaml.safe_load(Path(meta).read_text(encoding="utf-8")) or {})
    if meta is not None:
        return dict(meta)
    mp = meta_path(data)
    if mp.is_file():
        return dict(yaml.safe_load(mp.read_text(encoding="utf-8")) or {})
    return {}


# --------------------------------------------------------------------------------------------------- leitores
def split_header(h: str) -> tuple[str, str | None]:
    """``"alpha [deg]"`` → ``("alpha", "deg")``; ``"V_m_s"`` → ``("V_m_s", "m/s")``; ``"CL"`` → ``("CL", None)``."""
    from acdt.core.quantities import unit_from_key

    m = _HDR_UNIT.match(h)
    if m:
        u = m.group(2).strip()
        return m.group(1).strip(), (u if u not in ("", "-") else "1")
    return h.strip(), unit_from_key(h.strip())


def _num(s: str) -> float:
    s = s.strip()
    if s == "" or s.lower() in ("nan", "na", "null", "none"):
        return math.nan
    return float(s)


def read_csv_text(text: str, where: str = "csv") -> dict[str, tuple[Array, str | None]]:
    rows = [r for r in csv.reader(io.StringIO(text)) if r and not r[0].lstrip().startswith("#")]
    if not rows:
        raise IngestError(f"{where}: vazio")
    hdr = [split_header(h) for h in rows[0]]
    names = [h[0] for h in hdr]
    if len(set(names)) != len(names):
        raise IngestError(f"{where}: colunas repetidas {names}")
    cols: list[list[float]] = [[] for _ in names]
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != len(names):
            raise IngestError(f"{where}: linha {i} tem {len(r)} células, cabeçalho tem {len(names)}")
        for j, c in enumerate(r):
            try:
                cols[j].append(_num(c))
            except ValueError as e:
                raise IngestError(f"{where}: linha {i}, coluna '{names[j]}': '{c}' não é número") from e
    return {n: (np.asarray(c, dtype=float), u) for (n, u), c in zip(hdr, cols)}


def read_parquet(path: Path) -> dict[str, tuple[Array, str | None]]:
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except ImportError as e:
        raise IngestError("Parquet precisa de pandas + pyarrow (pip install 'acdt[dados]')") from e
    out: dict[str, tuple[Array, str | None]] = {}
    for col in df.columns:
        name, unit = split_header(str(col))
        try:
            out[name] = (np.asarray(df[col].to_numpy(dtype=float), dtype=float), unit)
        except (TypeError, ValueError):
            continue  # colunas de texto ficam de fora (não são canais numéricos)
    return out


def read_ulog(path: Path, topics: Iterable[str] | None = None) -> dict[str, tuple[Array, str | None]]:
    """PX4 ULog → canais ``tópico.campo`` (instância > 0: ``tópico_i.campo``). Tópicos diferentes têm bases de
    tempo diferentes: cada canal só tem sentido com o ``timestamp`` do mesmo tópico (não se reamostra). Unidade
    pelo sufixo do nome do campo (``true_airspeed_m_s`` → m/s; a convenção uORB coincide com a do acdt); campos
    sem sufixo reconhecido ficam com unidade não declarada."""
    try:
        from pyulog import ULog  # BSD-3-Clause
    except ImportError as e:
        raise IngestError("PX4 ULog precisa de pyulog (BSD-3-Clause; pip install 'acdt[dados]')") from e
    from acdt.core.quantities import unit_from_key

    ul = ULog(str(path), list(topics) if topics else None)
    out: dict[str, tuple[Array, str | None]] = {}
    for d in ul.data_list:
        base = d.name if d.multi_id == 0 else f"{d.name}_{d.multi_id}"
        for fld, arr in d.data.items():
            try:
                v = np.asarray(arr, dtype=float)
            except (TypeError, ValueError):
                continue
            out[f"{base}.{fld}"] = (v, "us" if fld == "timestamp" else unit_from_key(fld))
    return out


def detect_format(path: Path) -> str:
    s = path.suffix.lower()
    if s in (".csv", ".txt"):
        return "csv"
    if s in (".parquet", ".pq"):
        return "parquet"
    if s == ".ulg":
        return "ulog"
    if s in (".bin", ".tlog"):
        raise IngestError(f"{path.name}: log ArduPilot/MAVLink — o leitor pymavlink é LGPL-3.0 e não corre no processo; "
                          f"converta fora do processo (mavlogdump.py --format csv) e ingira o CSV")
    raise IngestError(f"{path.name}: formato desconhecido (use {FORMATS})")


def build(name: str, raw: Mapping[str, tuple[Array, str | None]], meta: Mapping[str, Any], *, fmt: str = "",
          file: Mapping[str, Any] | None = None, where: str = "") -> Dataset:
    """Monta o conjunto: aplica ``meta.channels`` (renomear, unidade declarada, incerteza) e valida."""
    m = _check_meta(meta, where or name)
    ch_meta: Mapping[str, Any] = m.get("channels") or {}
    unknown = set(ch_meta) - set(raw) - {str(v.get("rename")) for v in ch_meta.values() if isinstance(v, Mapping)}
    if unknown:
        raise IngestError(f"{where or name}: metadados de canais inexistentes {sorted(unknown)}")
    chans: dict[str, Channel] = {}
    for k, (vals, unit) in raw.items():
        cm = dict(ch_meta.get(k) or {})
        nk = str(cm.get("rename") or k)
        u = cm["unit"] if "unit" in cm else unit
        if u is not None:
            from acdt.core.quantities import same_dimension
            if not same_dimension(str(u), str(u)):
                raise IngestError(f"{where or name}: canal '{k}': unidade '{u}' desconhecida")
            u = str(u)
        if unit is not None and "unit" in cm and cm["unit"] is not None and unit != cm["unit"]:
            from acdt.core.quantities import same_dimension
            if not same_dimension(unit, str(cm["unit"])):
                raise IngestError(f"{where or name}: canal '{k}': cabeçalho diz '{unit}', metadados dizem "
                                  f"'{cm['unit']}' (dimensões diferentes)")
            vals = _affine(unit, str(cm["unit"]), k)(vals)
        chans[nk] = Channel(nk, np.asarray(vals, dtype=float), u,
                            standard_uncertainty(cm.get("uncertainty"), f"canal '{k}'"))
    lens = {c.values.size for c in chans.values()}
    if len(lens) > 1 and fmt != "ulog":
        raise IngestError(f"{where or name}: canais com comprimentos diferentes {sorted(lens)}")
    meta_out = {k: v for k, v in m.items() if k != "channels"}
    return Dataset(name, chans, meta_out, dict(file) if file else None, fmt)


def load(path: str | Path, meta: Mapping[str, Any] | str | Path | None = None, *, name: str | None = None,
         topics: Iterable[str] | None = None) -> Dataset:
    """Lê um ficheiro de dados medidos + metadados (``<ficheiro>.meta.yaml`` por omissão)."""
    from acdt.core.provenance import hash_input, note_input

    p = Path(path)
    if not p.is_file():
        raise IngestError(f"{p}: não existe")
    fmt = detect_format(p)
    m = _read_meta(p, meta)
    if fmt == "csv":
        raw = read_csv_text(p.read_text(encoding="utf-8-sig"), str(p))
    elif fmt == "parquet":
        raw = read_parquet(p)
    else:
        raw = read_ulog(p, topics or m.get("topics"))
    note_input(p)
    return build(name or str(m.get("name") or p.stem), raw, m, fmt=fmt, file=hash_input(p), where=str(p))


def from_arrays(name: str, columns: Mapping[str, tuple[Iterable[float], str | None]], meta: Mapping[str, Any]
                ) -> Dataset:
    """Conjunto em memória (testes, dados publicados transcritos no código com citação)."""
    raw = {k: (np.asarray(list(v), dtype=float), u) for k, (v, u) in columns.items()}
    return build(name, raw, meta, fmt="memoria")
