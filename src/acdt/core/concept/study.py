"""Concept-study record: the audit trail of an AI-driven conceptual trade (problem → requirements → alternatives →
tool calls → recommendation), saved as ``study.json`` and rendered as ``report.md``.

Nothing here computes or decides. The record separates what the agent *reasoned* (interpretation, assumptions
marked PRESSUPOSTO, derived requirements with their justification, alternatives, recommendation) from what the
deterministic tools *calculated* (every call with its arguments and result, in order), so a study can be audited
and replayed (``acdt concept replay``). Structure follows the requirements-traceability practice of
INCOSE (2015), "Systems Engineering Handbook", 4th ed., Wiley (stakeholder needs → system requirements →
alternatives → trade-off → decision record).
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import unicodedata
from pathlib import Path

KINDS = ("interpretation", "assumption", "question", "requirement", "alternative", "source", "finding",
         "recommendation", "note")
SCHEMA = "acdt.concept_study/1"


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()     # Vigilância → vigilancia
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:48].strip("_") or "study"


class Study:
    def __init__(self, title: str, problem: str, folder: Path, study_id: str | None = None):
        self.data = {"schema": SCHEMA, "id": study_id or _slug(title), "title": title, "problem": problem,
                     "created": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                     **{k + "s" if not k.endswith("s") else k: [] for k in KINDS if k != "recommendation"},
                     "recommendation": None, "calls": [], "comparisons": [], "files": {}}
        self.folder = Path(folder)

    # ------------------------------------------------------------------ persistence
    @classmethod
    def load(cls, path: Path) -> "Study":
        p = Path(path)
        if p.is_dir():
            p = p / "study.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        s = cls(d["title"], d["problem"], p.parent, d["id"])
        s.data = d
        return s

    def save(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        p = self.folder / "study.json"
        p.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        return p

    # ------------------------------------------------------------------ content
    def add(self, kind: str, content: dict | str) -> dict:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        item = {"text": content} if isinstance(content, str) else dict(content)
        if kind == "recommendation":
            self.data["recommendation"] = item
        else:
            key = kind + "s"
            item.setdefault("id", f"{kind[:3].upper()}{len(self.data[key]) + 1}")
            self.data[key].append(item)
        return item

    def log_call(self, tool: str, args: dict, result) -> int:
        seq = len(self.data["calls"]) + 1
        self.data["calls"].append({"seq": seq, "tool": tool, "args": args, "result": result})
        return seq

    # ------------------------------------------------------------------ report
    def report_md(self) -> str:
        d = self.data
        L = [f"# Estudo conceptual: {d['title']}", "",
             f"*Registo `{d['id']}` ({d['schema']}), criado {d['created']}. O raciocínio é do agente de IA; os "
             "números vêm das ferramentas determinísticas do acdt (secção Chamadas). Valores marcados PRESSUPOSTO "
             "não vêm de método nem de fonte.*", "", "## Problema (palavras do utilizador)", "", f"> {d['problem']}", ""]

        def sec(title, items, fmt):
            if items:
                L.extend([f"## {title}", ""])
                L.extend(fmt(i) for i in items)
                L.append("")
        sec("Interpretação", d["interpretations"], lambda i: f"* {i.get('text', '')}")
        sec("Pressupostos", d["assumptions"],
            lambda i: f"* **{i['id']}** PRESSUPOSTO — {i.get('text', '')}"
                      + (f" *Justificação:* {i['rationale']}" if i.get("rationale") else "")
                      + (f" *Fonte:* {i['source']}" if i.get("source") else ""))
        sec("Fontes consultadas", d["sources"],
            lambda i: f"* **{i['id']}** {i.get('text', i.get('what', ''))} — {i.get('url', '')}"
                      + (f" (consultado {i['retrieved']})" if i.get("retrieved") else ""))
        if d["requirements"]:
            L += ["## Requisitos derivados", "", "| id | requisito | métrica | limiar | justificação |",
                  "|---|---|---|---|---|"]
            for r in d["requirements"]:
                L.append(f"| {r['id']} | {r.get('text', '')} | {r.get('metric', '')} | {r.get('threshold', '')} | "
                         f"{r.get('justification', '')} |")
            L.append("")
        if d["alternatives"]:
            L += ["## Alternativas", "", "| id | descrição | avaliável | como / porque não |", "|---|---|---|---|"]
            for a in d["alternatives"]:
                L.append(f"| {a['id']} | {a.get('text', a.get('description', ''))} | "
                         f"{'sim' if a.get('evaluable', True) else 'não'} | {a.get('how', a.get('reason', ''))} |")
            L.append("")
        for c in d["comparisons"]:
            L += [f"## Comparação: {c.get('title', '')}", ""]
            obj = c["result"]["objectives"]
            cols = list(dict.fromkeys(list(obj) + list(c.get("show", []))))
            L.append("| alternativa | " + " | ".join(cols) + " | Pareto | restrições |")
            L.append("|---|" + "---|" * len(cols) + "---|---|")
            for r in c["result"]["rows"]:
                vals = [(f"{r['metrics'][k]:.4g}" if isinstance(r["metrics"].get(k), (int, float))
                         and not isinstance(r["metrics"].get(k), bool) else str(r["metrics"].get(k, "—")))
                        for k in cols]
                L.append(f"| {r['id']} | " + " | ".join(vals) + f" | {'sim' if r['pareto'] else 'não'} | "
                         f"{'; '.join(r['violations']) or 'ok'} |")
            L.append("")
            L.append("Objetivos: " + ", ".join(f"{k} ({'minimizar' if s == 'min' else 'maximizar'})"
                                              for k, s in obj.items()) + ". Frente de Pareto: "
                     + (", ".join(c["result"]["pareto"]) or "vazia") + ".")
            if c["result"].get("ranking"):
                L.append("Pesos dados pelo agente: " + ", ".join(f"{k} {w:.2f}" for k, w in
                                                                 c["result"]["weights"].items())
                         + "; ordenação: " + ", ".join(c["result"]["ranking"]) + ".")
            if c.get("plot"):
                L.append(f"\n![{c.get('title', '')}]({Path(c['plot']).name})")
            L.append("")
        sec("Constatações", d["findings"], lambda i: f"* **{i['id']}** {i.get('text', '')}")
        rec = d.get("recommendation")
        if rec:
            L += ["## Recomendação", "", rec.get("text", "")]
            for k, t in (("rationale", "Porquê"), ("sensitivities", "Sensibilidades"),
                         ("not_evaluated", "Fora do alcance das ferramentas"), ("next_steps", "Próximos passos")):
                if rec.get(k):
                    v = rec[k]
                    if isinstance(v, dict):
                        v = [f"{a}: {b:.3g}" if isinstance(b, float) else f"{a}: {b}" for a, b in v.items()]
                    L += ["", f"**{t}:**"] + ([f"* {x}" for x in v] if isinstance(v, list) else [str(v)])
            L.append("")
        sec("Perguntas ao utilizador", d["questions"], lambda i: f"* **{i['id']}** {i.get('text', '')}")
        sec("Notas", d["notes"], lambda i: f"* {i.get('text', '')}")
        if d["calls"]:
            L += ["## Chamadas às ferramentas (determinísticas)", "", "| # | ferramenta | argumentos (resumo) |",
                  "|---|---|---|"]
            for c in d["calls"]:
                a = json.dumps(c["args"], ensure_ascii=False)
                L.append(f"| {c['seq']} | `{c['tool']}` | `{a[:160] + ('…' if len(a) > 160 else '')}` |")
            L += ["", "Os resultados completos estão em `study.json` (`calls[].result`); `acdt concept replay "
                  "study.json` volta a correr as chamadas e confirma que dão o mesmo resultado.", ""]
        return "\n".join(L)

    def write_report(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        p = self.folder / "report.md"
        p.write_text(self.report_md(), encoding="utf-8")
        self.data["files"]["report.md"] = "report.md"
        self.save()
        return p
