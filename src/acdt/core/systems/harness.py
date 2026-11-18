"""Electrical harness model: connectors, wires, netlist; wire gauge sizing; exports.

* Conductor resistance R = ρ L / A with annealed-copper resistivity
  ρ20 = 1.7241e-8 Ω·m (IEC 60028) and temperature coefficient α20 = 0.00393 /K.
* AWG diameters: ASTM B258, d_n = 0.127 mm · 92^((36−n)/39).
* Gauge selection: smallest conductor satisfying (i) ampacity (from a user /
  manufacturer table — SAE AS50881 derating curves are the reference; the
  default table below is EXAMPLE data) and (ii) the allowed voltage drop for
  the round-trip length (SAE AS50881 voltage-drop practice; default limit is a
  user assumption).
* Exports: WireViz YAML (WireViz, GPL-3.0, run as an external tool),
  Graphviz DOT, CSV netlist, KiCad s-expression netlist (format "E", :func:`kicad_netlist`).
"""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field

RHO_CU_20 = 1.7241e-8
ALPHA_CU = 0.00393
DENSITY_CU = 8890.0  # kg/m^3, annealed copper standard density (IEC 60028)

# EXAMPLE single-wire chassis ampacity [A] by AWG (order of magnitude; replace with SAE AS50881 /
# wire manufacturer derating for bundle size, altitude and temperature class).
EXAMPLE_AMPACITY_AWG = {28: 1.4, 26: 2.2, 24: 3.5, 22: 5.0, 20: 7.5, 18: 10, 16: 13, 14: 17, 12: 23, 10: 33,
                        8: 46, 6: 60, 4: 80}


def awg_diameter_m(n: int) -> float:
    """ASTM B258 AWG diameter."""
    return 0.127e-3 * 92 ** ((36 - n) / 39)


def awg_area_m2(n: int) -> float:
    return math.pi / 4 * awg_diameter_m(n) ** 2


def resistance(length_m: float, area_m2: float, temp_c: float = 20.0) -> float:
    return RHO_CU_20 * (1 + ALPHA_CU * (temp_c - 20)) * length_m / area_m2


@dataclass
class GaugeChoice:
    awg: int | None
    area_mm2: float
    voltage_drop_V: float
    drop_fraction: float
    ampacity_A: float
    governed_by: str


def select_gauge(current_A: float, one_way_length_m: float, v_supply: float, max_drop_fraction: float = 0.03,
                 temp_c: float = 60.0, ampacity: dict[int, float] | None = None) -> GaugeChoice:
    amp = ampacity or EXAMPLE_AMPACITY_AWG
    for n in sorted(amp, reverse=True):  # thinnest first
        A = awg_area_m2(n)
        dv = current_A * resistance(2 * one_way_length_m, A, temp_c)
        if amp[n] >= current_A and dv <= max_drop_fraction * v_supply:
            gov = "voltage drop" if amp.get(n + 2, 0) >= current_A else "ampacity"
            return GaugeChoice(n, A * 1e6, dv, dv / v_supply, amp[n], gov)
    return GaugeChoice(None, math.nan, math.nan, math.nan, math.nan, "no gauge in table satisfies limits")


@dataclass
class Connector:
    name: str
    pins: list[str]
    part: str = ""


@dataclass
class Wire:
    name: str
    frm: tuple[str, str]  # (connector, pin label)
    to: tuple[str, str]
    signal: str
    current_A: float = 0.1
    length_m: float = 0.5
    v_supply: float = 5.0
    awg: int | None = None
    color: str = ""


@dataclass
class Harness:
    name: str
    connectors: dict[str, Connector] = field(default_factory=dict)
    wires: list[Wire] = field(default_factory=list)

    def add_connector(self, c: Connector):
        self.connectors[c.name] = c
        return c

    def connect(self, w: Wire):
        for cname, pin in (w.frm, w.to):
            if cname not in self.connectors or pin not in self.connectors[cname].pins:
                raise KeyError(f"{w.name}: unknown endpoint {cname}:{pin}")
        self.wires.append(w)
        return w

    def size_wires(self, max_drop_fraction: float = 0.03, temp_c: float = 60.0, ampacity=None):
        out = {}
        for w in self.wires:
            g = select_gauge(w.current_A, w.length_m, w.v_supply, max_drop_fraction, temp_c, ampacity)
            w.awg = g.awg
            out[w.name] = g
        return out

    def conductor_mass(self) -> float:
        """Copper mass [kg] = Σ length · A_awg · ρ_Cu (IEC 60028 density). Wires without a gauge are skipped."""
        return sum(w.length_m * awg_area_m2(w.awg) * DENSITY_CU for w in self.wires if w.awg is not None)

    def mass(self, insulation_factor: float = 1.3, connector_mass_kg: float = 0.01) -> float:
        """Harness mass [kg]: conductor mass x (1 + insulation/jacket/sleeving allowance) + connectors.
        Both factors are USER ASSUMPTIONS (defaults are placeholders): take them from the wire
        datasheet (mass per km, SAE AS22759 / EN 2267 families) and the connector datasheets."""
        return self.conductor_mass() * insulation_factor + connector_mass_kg * len(self.connectors)

    def netlist(self) -> dict[str, list[str]]:
        nets: dict[str, list[str]] = {}
        for w in self.wires:
            nets.setdefault(w.signal, [])
            for c, p in (w.frm, w.to):
                if f"{c}.{p}" not in nets[w.signal]:
                    nets[w.signal].append(f"{c}.{p}")
        return nets

    def to_csv(self) -> str:
        s = io.StringIO()
        wr = csv.writer(s)
        wr.writerow(["wire", "signal", "from", "to", "current_A", "length_m", "awg"])
        for w in self.wires:
            wr.writerow([w.name, w.signal, ":".join(w.frm), ":".join(w.to), w.current_A, w.length_m, w.awg])
        return s.getvalue()

    def to_wireviz_yaml(self) -> str:
        """WireViz input (connectors / cables / connections) — one cable per wire."""
        import yaml

        doc = {"connectors": {c.name: {"pinlabels": c.pins, **({"pn": c.part} if c.part else {})}
                              for c in self.connectors.values()},
               "cables": {}, "connections": []}
        for w in self.wires:
            doc["cables"][w.name] = {"wirecount": 1, "gauge": f"{w.awg} AWG" if w.awg else "TBD",
                                     "length": w.length_m, "colors": [w.color] if w.color else ["BK"]}
            doc["connections"].append([{w.frm[0]: [w.frm[1]]}, {w.name: [1]}, {w.to[0]: [w.to[1]]}])
        return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)

    def to_dot(self) -> str:
        lines = [f'graph "{self.name}" {{', "  rankdir=LR; node [shape=record];"]
        for c in self.connectors.values():
            ports = "|".join(f"<{p}> {p}" for p in c.pins)
            lines.append(f'  "{c.name}" [label="{c.name}|{{{ports}}}"];')
        for w in self.wires:
            lines.append(f'  "{w.frm[0]}":"{w.frm[1]}" -- "{w.to[0]}":"{w.to[1]}" '
                         f'[label="{w.name} {w.signal} {w.awg or "?"}AWG"];')
        lines.append("}")
        return "\n".join(lines)


def _q(x) -> str:
    return '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'


def kicad_netlist(h: "Harness", source: str = "acdt", date: str = "", footprint=None) -> str:
    """KiCad s-expression netlist (format version "E", as written by Eeschema "Export Netlist → KiCad" and read by
    Pcbnew "Import Netlist" / kinparse), for harness ↔ PCB co-design.

    Each connector becomes a component (ref = connector name, value = part number) with pins numbered 1..n in the
    order of ``Connector.pins``; the pin label goes to ``pinfunction``. Each signal becomes a net named
    ``/<signal>``. ``footprint(connector) -> str`` chooses the footprint; default: a 2.54 mm 1×n pin header
    (``Connector_PinHeader_2.54mm:PinHeader_1x<n>_P2.54mm_Vertical``, KiCad standard library) — a PLACEHOLDER to
    replace by the real connector footprint."""
    fp = footprint or (lambda c: f"Connector_PinHeader_2.54mm:PinHeader_1x{len(c.pins):02d}_P2.54mm_Vertical")
    L = ['(export (version "E")', f"  (design (source {_q(source)}) (date {_q(date)}) (tool {_q('acdt harness')}))",
         "  (components"]
    for c in h.connectors.values():
        L.append(f"    (comp (ref {_q(c.name)}) (value {_q(c.part or 'CONN')}) (footprint {_q(fp(c))})")
        L.append(f"      (libsource (lib {_q('Connector_Generic')}) (part {_q(f'Conn_01x{len(c.pins):02d}')}) "
                 f"(description {_q('acdt harness connector')})))")
    L.append("  )")
    L.append("  (nets")
    for code, (sig, nodes) in enumerate(h.netlist().items(), start=1):
        L.append(f"    (net (code {_q(code)}) (name {_q('/' + sig)})")
        for n in nodes:
            cname, pin = n.split(".", 1)
            idx = h.connectors[cname].pins.index(pin) + 1
            L.append(f"      (node (ref {_q(cname)}) (pin {_q(idx)}) (pinfunction {_q(pin)}))")
        L[-1] += ")"
    L.append("  )")
    L.append(")")
    return "\n".join(L) + "\n"
