"""Fault tree analysis (FTA) — ARP4761 / NUREG-0492 style, implemented in-house.

* Gates: AND, OR, k-of-n (``KOFN``, k failures among n inputs fail the gate).
* Basic events with a constant failure rate λ [1/h] and an exposure time T [h]:
  q = 1 − exp(−λ T) (Fault Tree Handbook, NUREG-0492, Vesely et al. 1981). A latent (dormant) failure that is only revealed by an inspection every
  τ hours uses T = τ (conservative upper value of the exposure, ARP4761 Appendix D, FTA "exposure time"); a
  directly evident failure uses the flight time.
* Minimal cut sets by MOCUS (Fussell & Vesely 1972; NUREG-0492) with absorption.
* Top-event probability exact by Shannon decomposition on the structure function (no rare-event error, also with
  repeated events); the rare-event (sum of cut-set products) value is also reported.
* Average probability per flight hour = P_top(T_flight) / T_flight (ARP4761 / AC 23.1309-1E "average probability
  per flight hour").
* Fussell–Vesely importance per basic event.

Open-source options reviewed (THIRD_PARTY.md): SCRAM (GPL-3.0, not usable in-process) and ``cutsets`` (MIT, MOCUS
only). The small tree sizes of conceptual design make an own implementation the simplest licence-clean path.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations


@dataclass
class BasicEvent:
    id: str
    name: str = ""
    rate_per_h: float | None = None   # λ [1/h]
    prob: float | None = None         # fixed probability (overrides λ)
    exposure_h: float | None = None   # None -> flight time of the analysis
    source: str = ""
    latent: bool = False

    def q(self, t_flight: float) -> float:
        if self.prob is not None:
            return float(self.prob)
        lam = float(self.rate_per_h or 0.0)
        T = float(self.exposure_h if self.exposure_h is not None else t_flight)
        return -math.expm1(-lam * T)


@dataclass
class Gate:
    id: str
    kind: str                 # "AND" | "OR" | "KOFN"
    inputs: list[str]
    name: str = ""
    k: int = 1

    def __post_init__(self):
        self.kind = self.kind.upper()
        if self.kind not in ("AND", "OR", "KOFN"):
            raise ValueError(f"gate {self.id}: kind {self.kind}")
        if self.kind == "KOFN" and not (1 <= self.k <= len(self.inputs)):
            raise ValueError(f"gate {self.id}: k={self.k} with {len(self.inputs)} inputs")


@dataclass
class FaultTree:
    top: str
    gates: dict[str, Gate] = field(default_factory=dict)
    events: dict[str, BasicEvent] = field(default_factory=dict)
    name: str = ""

    # ---------------- building ----------------
    def add_event(self, ev: BasicEvent) -> str:
        self.events[ev.id] = ev
        return ev.id

    def add_gate(self, g: Gate) -> str:
        self.gates[g.id] = g
        return g.id

    def _check(self):
        for g in self.gates.values():
            for i in g.inputs:
                if i not in self.gates and i not in self.events:
                    raise KeyError(f"gate {g.id}: unknown input {i}")
        if self.top not in self.gates and self.top not in self.events:
            raise KeyError(f"top {self.top} undefined")

    def _expand(self, g: Gate) -> list[Gate]:
        """KOFN -> OR of ANDs of every k-subset (used by MOCUS)."""
        return [Gate(f"{g.id}#{n}", "AND", list(c)) for n, c in enumerate(combinations(g.inputs, g.k))]

    # ---------------- minimal cut sets (MOCUS) ----------------
    def minimal_cut_sets(self, max_order: int = 8) -> list[frozenset]:
        self._check()
        rows: list[list[str]] = [[self.top]]
        done: list[frozenset] = []
        while rows:
            r = rows.pop()
            gi = next((x for x in r if x in self.gates), None)
            if gi is None:
                s = frozenset(r)
                if len(s) <= max_order:
                    done.append(s)
                continue
            g = self.gates[gi]
            rest = [x for x in r if x != gi]
            if g.kind == "AND":
                rows.append(rest + list(g.inputs))
            elif g.kind == "OR":
                for i in g.inputs:
                    rows.append(rest + [i])
            else:
                for sub in combinations(g.inputs, g.k):
                    rows.append(rest + list(sub))
        done = sorted(set(done), key=lambda s: (len(s), sorted(s)))
        mcs: list[frozenset] = []
        for s in done:
            if not any(m <= s for m in mcs):
                mcs.append(s)
        return mcs

    # ---------------- probabilities ----------------
    def _formula(self, node: str):
        if node in self.events:
            return ("E", node)
        g = self.gates[node]
        ch = tuple(self._formula(i) for i in g.inputs)
        if g.kind == "KOFN":
            return ("K", g.k, ch)
        return (g.kind, ch)

    def top_probability(self, t_flight: float = 1.0) -> float:
        """Exact P(top) over the exposure, by Shannon decomposition on the basic events."""
        self._check()
        q = {e: ev.q(t_flight) for e, ev in self.events.items()}
        f = self._formula(self.top)
        order = sorted(self.events)

        def cond(f, e, v):
            t = f[0]
            if t == "E":
                return (v if f[1] == e else f)
            if t == "K":
                k, ch = f[1], [cond(c, e, v) for c in f[2]]
                ones = sum(1 for c in ch if c is True)
                ch = [c for c in ch if c not in (True, False)]
                k2 = k - ones
                if k2 <= 0:
                    return True
                if k2 > len(ch):
                    return False
                if k2 == 1:
                    return ("OR", tuple(ch)) if len(ch) > 1 else ch[0]
                if k2 == len(ch):
                    return ("AND", tuple(ch))
                return ("K", k2, tuple(ch))
            ch = [cond(c, e, v) for c in f[1]]
            if t == "AND":
                if any(c is False for c in ch):
                    return False
                ch = [c for c in ch if c is not True]
                if not ch:
                    return True
            else:
                if any(c is True for c in ch):
                    return True
                ch = [c for c in ch if c is not False]
                if not ch:
                    return False
            return ch[0] if len(ch) == 1 else (t, tuple(ch))

        def events_in(f, acc):
            if f in (True, False):
                return acc
            if f[0] == "E":
                acc.add(f[1])
            else:
                for c in (f[2] if f[0] == "K" else f[1]):
                    events_in(c, acc)
            return acc

        @lru_cache(maxsize=None)
        def P(f):
            if f is True:
                return 1.0
            if f is False:
                return 0.0
            if f[0] == "E":
                return q[f[1]]
            evs = events_in(f, set())
            e = min(evs, key=order.index)
            return q[e] * P(cond(f, e, True)) + (1.0 - q[e]) * P(cond(f, e, False))

        return float(P(f))

    def rare_event(self, t_flight: float = 1.0) -> float:
        q = {e: ev.q(t_flight) for e, ev in self.events.items()}
        return float(sum(math.prod(q[e] for e in s) for s in self.minimal_cut_sets()))

    def per_flight_hour(self, t_flight: float) -> float:
        """Average probability per flight hour (ARP4761): P_top over one flight of T hours divided by T."""
        return self.top_probability(t_flight) / max(t_flight, 1e-12)

    def importance(self, t_flight: float = 1.0) -> dict[str, float]:
        """Fussell–Vesely importance: share of the rare-event top probability through cut sets with the event."""
        q = {e: ev.q(t_flight) for e, ev in self.events.items()}
        mcs = self.minimal_cut_sets()
        tot = sum(math.prod(q[e] for e in s) for s in mcs) or 1e-300
        return {e: sum(math.prod(q[x] for x in s) for s in mcs if e in s) / tot for e in self.events}

    def summary(self, t_flight: float) -> dict:
        mcs = self.minimal_cut_sets()
        q = {e: ev.q(t_flight) for e, ev in self.events.items()}
        rows = sorted(({"cut_set": sorted(s), "order": len(s), "p": math.prod(q[e] for e in s)} for s in mcs),
                      key=lambda r: -r["p"])
        return {"name": self.name, "top": self.top, "t_flight_h": t_flight,
                "P_top": self.top_probability(t_flight), "P_rare_event": self.rare_event(t_flight),
                "P_per_fh": self.per_flight_hour(t_flight), "n_cut_sets": len(mcs),
                "min_order": min((len(s) for s in mcs), default=0),
                "single_point_failures": [r["cut_set"][0] for r in rows if r["order"] == 1],
                "cut_sets": rows[:25], "importance_FV": self.importance(t_flight)}

    # ---------------- plotting ----------------
    def plot(self, path, title: str = "", t_flight: float = 1.0, max_label: int = 26):
        """Top-down fault-tree drawing (matplotlib): gates as labelled boxes with the gate type, basic events as
        circles with λ and q; tidy layout by leaf counting."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch, Circle

        pos: dict[str, tuple[float, float]] = {}
        nodes: list[tuple[str, str, int]] = []   # (uid, id, depth) — repeated events drawn per occurrence

        def leaves(n):
            return 1 if n in self.events else sum(leaves(i) for i in self.gates[n].inputs)

        def place(n, x0, depth, path_id):
            w = leaves(n)
            uid = f"{path_id}/{n}"
            pos[uid] = (x0 + w / 2.0, -depth)
            nodes.append((uid, n, depth))
            if n in self.gates:
                x = x0
                for i in self.gates[n].inputs:
                    cu = place(i, x, depth + 1, uid)
                    edges.append((uid, cu))
                    x += leaves(i)
            return uid

        edges: list[tuple[str, str]] = []
        place(self.top, 0.0, 0, "")
        W = leaves(self.top)
        D = max(d for _, _, d in nodes) + 1
        fig, ax = plt.subplots(figsize=(max(7.0, 1.55 * W), 1.55 * D + 1.0))
        for a, b in edges:
            (x1, y1), (x2, y2) = pos[a], pos[b]
            ax.plot([x1, x1, x2, x2], [y1 - 0.22, (y1 + y2) / 2, (y1 + y2) / 2, y2 + 0.22], "k-", lw=0.8)
        P = {}
        for uid, n, d in nodes:
            x, y = pos[uid]
            if n in self.gates:
                g = self.gates[n]
                sub = FaultTree(n, self.gates, self.events)
                P[n] = P.get(n) or sub.top_probability(t_flight)
                kind = {"AND": "E (AND)", "OR": "OU (OR)", "KOFN": f"{g.k}-de-{len(g.inputs)}"}[g.kind]
                col = {"AND": "#cfe3ff", "OR": "#ffe2c2", "KOFN": "#e3d4ff"}[g.kind]
                ax.add_patch(FancyBboxPatch((x - 0.46, y - 0.22), 0.92, 0.44, boxstyle="round,pad=0.02",
                                            fc=col, ec="k", lw=0.8))
                ax.text(x, y + 0.07, (g.name or n)[:max_label], ha="center", va="center", fontsize=6.5)
                ax.text(x, y - 0.12, f"{kind}  P={P[n]:.2e}", ha="center", va="center", fontsize=6)
            else:
                ev = self.events[n]
                ax.add_patch(Circle((x, y), 0.2, fc="#e8ffe8" if not ev.latent else "#fff6c8", ec="k", lw=0.8))
                ax.text(x, y + 0.03, n[:12], ha="center", va="center", fontsize=5.5)
                lam = f"λ={ev.rate_per_h:.1e}" if ev.rate_per_h is not None else f"p={ev.prob:.1e}"
                ax.text(x, y - 0.33, f"{(ev.name or n)[:max_label]}\n{lam}  q={ev.q(t_flight):.1e}"
                        + ("\nlatente" if ev.latent else ""), ha="center", va="top", fontsize=5.2)
        ax.set_xlim(-0.2, W + 0.2)
        ax.set_ylim(-D - 0.2, 0.6)
        ax.axis("off")
        ax.set_title(title or self.name, fontsize=9)
        fig.tight_layout()
        fig.savefig(path, dpi=130)
        plt.close(fig)
        return path
