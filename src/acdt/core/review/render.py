# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Formatos do relatório de revisão: Markdown, HTML autónomo (figuras embutidas em base64) e PDF opcional.

O relatório é primeiro uma lista de blocos (título, parágrafo, tabela, lista, figura); Markdown e HTML saem dos
mesmos blocos, por isso dizem o mesmo. O PDF só é gerado se o WeasyPrint (BSD-3-Clause) estiver instalado; não
é dependência do acdt.
"""
from __future__ import annotations

import base64
import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

Block = tuple[Any, ...]

STATUS_LABEL = {"cumpre": "cumpre", "nao_cumpre": "NÃO CUMPRE", "insuficiente": "insuficiente",
                "revisao_humana": "revisão humana", "dispensado": "dispensado"}
VERDICT_LABEL = {"pronto": "PRONTO", "nao_pronto": "NÃO PRONTO", "insuficiente": "INSUFICIENTE"}


def num(x: Any) -> str:
    """Número para o relatório: ``None`` = desconhecido (—), nunca zero; 4 algarismos significativos."""
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "sim" if x else "não"
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        return f"{x:.4g}"
    if isinstance(x, (list, tuple)):
        return "[" + ", ".join(num(v) for v in x) + "]"
    if isinstance(x, Mapping):
        return ", ".join(f"{k}={num(v)}" for k, v in x.items())
    return str(x)


def unit(u: Any) -> str:
    return "(não declarada)" if u is None else ("—" if u in ("", "1") else str(u))


def _short(h: Any, n: int = 12) -> str:
    return str(h)[:n] if h else "—"


# --------------------------------------------------------------------------------------------- blocos
def blocks(r: Mapping[str, Any], figure_dir: str = "figuras") -> list[Block]:
    B: list[Block] = []
    d = r["design"]
    v = r["verdict"]
    st = r["standard"]
    B.append(("h", 1, f"Relatório de revisão {r['gate']} — {d.get('name')}"))
    B.append(("kv", [("Revisão", f"{r['gate']} ({r['gate_title']})"),
                     ("Norma", f"{st['id']} ({st['effective']}), {st['table']}, §{st['section']}"),
                     ("Fonte", st["url"]),
                     ("Projeto", f"{d.get('name')} — domínio {d.get('domain')}, {d.get('schema')}, revisão "
                                 f"{d.get('revision')}, atualizado {d.get('updated_utc')}"),
                     ("Entrada", f"{d.get('input') or '—'} (SHA-256 {_short(d.get('input_sha256'))})"),
                     ("Gerado", f"{r['generated_utc']} (acdt report, {r['schema']})")]))
    B.append(("p", f"Objetivo da revisão (NPR, {st['section']}): \"{r['gate_purpose']}\""))

    B.append(("h", 2, "1. Veredito"))
    B.append(("verdict", v["status"], VERDICT_LABEL[v["status"]]))
    c = v["counts"]
    B.append(("p", f"Critérios: {c['cumpre']} cumpre, {c['nao_cumpre']} não cumpre, {c['insuficiente']} "
                   f"insuficiente, {c['dispensado']} dispensado (automáticos: {v['n_automaticos']}); "
                   f"{c['revisao_humana']} para revisão humana."))
    if v["motivos"]:
        B.append(("p", "Decidem o veredito: " + ", ".join(v["motivos"]) + "."))
    B.append(("p", f"Âmbito: {v['ambito']}. {r['nota']}."))
    B.append(("p", "Regra: NÃO PRONTO se algum critério automático não cumpre; INSUFICIENTE se nenhum falha mas "
                   "falta evidência para algum; PRONTO só com todos os automáticos a cumprir."))

    B.append(("h", 2, "2. Critérios de entrada e de sucesso"))
    B.append(("p", f"Critérios de {st['id']} {st['table']} (excertos literais). Adaptação: {st['tailoring']} "
                   "A ligação entre o texto da NPR e o teste automático é uma interpretação do acdt "
                   "(PRESSUPOSTO), indicada em cada linha."))
    B.append(("table", ["ID", "Fase", "Critério (NPR)", "Avaliação", "Estado", "Detalhe", "Evidência"],
              [[k["id"], k["phase"], k["quote"], k["interpretacao"] if k["automatico"] else "revisão humana",
                STATUS_LABEL[k["status"]], k["detail"], "; ".join(k["evidence"]) or "—"] for k in r["criteria"]]))

    rq = r["requirements"]
    B.append(("h", 2, "3. Conformidade com os requisitos"))
    if not rq["present"]:
        B.append(("p", "Sem matriz de verificação: conformidade desconhecida."))
    else:
        cnt = ", ".join(f"{k} {n}" for k, n in rq["counts"].items())
        B.append(("p", f"Fonte: {rq['fonte']}. Estados: {cnt}. Fração avaliada: {num(rq['fracao_avaliada'])}. "
                       "nao_avaliado e desconhecido nunca contam como passa."))
        B.append(("table", ["ID", "Grandeza", "Limiar", "Valor", "Unidade", "Margem", "Estado", "Método",
                            "Fid. exig./aval.", "Evidência"],
                  [[x["id"] + (" (dispensa)" if x.get("dispensa") else ""), x.get("quantity") or "—",
                    x.get("display") or num(x.get("threshold")), num(x.get("value")),
                    x.get("unit") or "—", num(x.get("margin")), x.get("status"), x.get("method") or "—",
                    f"{x.get('fidelity_required') or '—'}/{x.get('fidelity_evaluated') or '—'}",
                    x.get("evidence") or "—"] for x in rq["rows"]]))
        if rq["requisitos_sem_avaliador"]:
            B.append(("p", "Requisitos sem avaliador: " + ", ".join(rq["requisitos_sem_avaliador"]) + "."))
        if rq["avaliadores_sem_requisito"]:
            B.append(("p", "Verificações calculadas sem requisito associado: "
                      + ", ".join(rq["avaliadores_sem_requisito"]) + "."))

    B.append(("h", 2, "4. Resumo do projeto"))
    if d["headline"]:
        B.append(("table", ["Grandeza", "Valor", "Unidade", "P5", "P50", "P95", "Nível", "Disciplina", "Caminho"],
                  [[h["name"], num(h["value"]), unit(h["unit"]) if h["path"] else "—", num(h.get("p5")),
                    num(h.get("p50")), num(h.get("p95")), h.get("level") or "—", h.get("discipline") or "—",
                    h.get("path") or h.get("nota", "—")] for h in d["headline"]]))
    else:
        B.append(("p", "O domínio não declara grandezas de resumo (perfil genérico); ver as disciplinas abaixo."))
    if d["definition_requirements"]:
        B.append(("p", "Requisitos de entrada (SI):"))
        B.append(("table", ["Chave", "Valor (SI)", "Unidade", "Escrito", "Fonte"],
                  [[x["key"], num(x["value"]), unit(x["unit"]),
                    f"{num(x['raw'])} {x.get('raw_unit') or ''}".strip(), x.get("source") or "—"]
                   for x in d["definition_requirements"]]))

    f = r["fidelity"]
    B.append(("h", 2, "5. Fidelidade por disciplina"))
    B.append(("p", f"Nível exigido às disciplinas primárias nesta revisão: {f['required_level']} ({f['pressuposto']})."))
    B.append(("table", ["Disciplina", "Níveis", "Máximo", "Primária", "Exigido", "Estado", "Origem", "Método",
                        "Sem unidade"],
              [[x["discipline"], ", ".join(x["levels"]) or "—", x["max_level"] or "—", num(x["primary"]),
                x["required"] or "—", x["status"], x["fidelity"] or "—", x["method"] or "—",
                num(x["n_sem_unidade"])] for x in f["rows"]]))
    B.append(("p", "Ainda em L0/L1: " + (", ".join(f["ainda_L0_L1"]) or "nenhuma") + "."))

    oi = r["open_items"]
    B.append(("h", 2, "6. Itens em aberto e riscos"))
    if oi:
        B.append(("table", ["Severidade", "Categoria", "ID", "Descrição", "Fonte"],
                  [[i["severidade"], i["categoria"], i["id"], i["descricao"], i["fonte"]] for i in oi]))
    else:
        B.append(("p", "Nenhum item em aberto nos registos (os critérios de revisão humana continuam pendentes)."))

    u = r["uq"]
    B.append(("h", 2, "7. Incerteza"))
    if not u["present"]:
        B.append(("p", "Sem estudo de incerteza: a probabilidade de cumprir os requisitos é desconhecida."))
    for s in u["studies"]:
        B.append(("p", f"{s['file']} (SHA-256 {_short(s['sha256'])}): {s['method']}, n = {num(s['n'])}, semente "
                       f"{num(s['seed'])}; modelo: {s['model']}."))
        if s["metrics"]:
            B.append(("table", ["Métrica", "n", "Média", "P5", "P50", "P95"],
                      [[m["metric"], num(m["n"]), num(m["mean"]), num(m["p5"]), num(m["p50"]), num(m["p95"])]
                       for m in s["metrics"]]))
        if s["requirements"]:
            B.append(("table", ["Requisito", "P(passa)", "IC", "P(no_limite)", "P(falha)", "Alvo", "Estado"],
                      [[q["id"], num(q["p_passa"]), num(q["p_passa_ic"]), num(q["p_no_limite"]), num(q["p_falha"]),
                        num(q["alvo"]), q["estado"] or "—"] for q in s["requirements"]]))
    if u["design_db"]:
        B.append(("p", "Incerteza guardada no estado de projeto:"))
        B.append(("table", ["Grandeza", "Unidade", "Tipo", "P5", "P50", "P95", "σ", "Fonte"],
                  [[x["path"], unit(x["unit"]), x["kind"] or "—", num(x["p5"]), num(x["p50"]), num(x["p95"]),
                    num(x["sd"]), x["source"] or "—"] for x in u["design_db"]]))

    m = r["mdo"]
    B.append(("h", 2, "8. MDO e frente de Pareto"))
    if not m["present"]:
        B.append(("p", "Sem estudo MDO registado."))
    for s in m["studies"]:
        obj = ", ".join(f"{o['sense']} {o['metric']}" for o in s["objectives"])
        B.append(("p", f"{s['file']} (SHA-256 {_short(s['sha256'])}): estratégia {s['strategy']}; objetivos {obj}; "
                       f"variáveis {', '.join(s['design_variables'])}; {num(s['n_evaluations'])} avaliações, "
                       f"{num(s['n_failed'])} falhadas, {num(s['n_feasible'])} viáveis, {s['n_pareto']} na frente."))
        if s["chosen"]:
            B.append(("p", f"Escolhido: #{s['chosen']['id']} x = {num(s['chosen']['x'])}; objetivos "
                           f"{num(s['chosen']['objectives'])}" + (f" (joelho: {s['knee'].get('method')})"
                                                                  if s.get("knee") else "") + "."))
        else:
            B.append(("p", "Nenhum projeto viável escolhido."))
        if s["pareto"]:
            B.append(("table", ["#", "x", "Objetivos"],
                      [[str(p["id"]), num(p["x"]), num(p["objectives"])] for p in s["pareto"]]))
            if s["pareto_truncado"]:
                B.append(("p", f"(primeiros {len(s['pareto'])} de {s['n_pareto']} pontos da frente)"))

    w = r["vv"]
    B.append(("h", 2, "9. V&V dos modelos"))
    if not w["present"]:
        B.append(("p", "Sem relatório de V&V: a validade dos modelos usados não está demonstrada neste registo."))
    for s in w["reports"]:
        B.append(("p", f"{s['file']} (SHA-256 {_short(s['sha256'])}): registo {s['registry_version']}, custo "
                       f"máximo {s['max_cost']}; {num(s['counts'])}."))
        B.append(("table", ["Caso", "Disciplina", "Tipo", "Estado", "Mensagem"],
                  [[k["id"], k["discipline"], k["kind"], k["status"], k["message"] or "—"] for k in s["cases"]]))

    cal = r["calibration"]
    B.append(("h", 2, "10. Calibração contra ensaio"))
    if not cal["present"]:
        B.append(("p", "Sem calibração registada."))
    for s in cal["records"]:
        B.append(("p", f"{s['file']} (SHA-256 {_short(s['sha256'])}): {s['name']} — {s['discipline']} "
                       f"{s['level']}, método {s['method']} ({s['reference']}); decisão {s['decision']}"
                       + ("; dados SINTÉTICOS" if s["synthetic"] else "") + "."))
        B.append(("table", ["Parâmetro", "Valor", "σ", "Unidade", "Decisão", "Motivos"],
                  [[p["name"], num(p["value"]), num(p["sd"]), unit(p["unit"]), p["decision"],
                    "; ".join(p["reasons"]) or "—"] for p in s["parameters"]]))

    B.append(("h", 2, "11. Rastreabilidade da evidência"))
    B.append(("p", "SHA-256 atual de cada ficheiro e, quando outro registo o guardou, a comparação: confere, "
                   "difere, sem_registo ou em_falta."))
    B.append(("table", ["Papel", "Ficheiro", "SHA-256", "Estado"],
              [[t["role"], t["path"], t["sha256"] or "—", t["status"]] for t in r["traceability"]]))

    B.append(("h", 2, "12. Figuras"))
    if not r["figures"]:
        B.append(("p", "Nenhuma figura já produzida nas pastas do projeto."))
    for fg in r["figures"]:
        B.append(("img", fg["path"], f"{figure_dir}/{Path(fg['path']).name}", f"{fg['path']} (SHA-256 "
                                                                              f"{_short(fg['sha256'])})"))
    ov = r["overrides"]
    if ov["waivers"] or ov["tailoring"] or r["profile_notes"] or r["warnings"]:
        B.append(("h", 2, "13. Dispensas, adaptações e notas"))
        items = [f"dispensa {k}: {j}" for k, j in ov["waivers"].items()]
        items += [f"adaptação {k}: {j}" for k, j in ov["tailoring"].items()]
        items += list(r["profile_notes"]) + [f"aviso: {x}" for x in r["warnings"]]
        B.append(("ul", items))
    return B


# ------------------------------------------------------------------------------------------- Markdown
def _md_cell(s: Any) -> str:
    return str(s).replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def to_markdown(r: Mapping[str, Any], figure_dir: str = "figuras") -> str:
    out: list[str] = []
    for b in blocks(r, figure_dir):
        k = b[0]
        if k == "h":
            out += ["#" * b[1] + " " + b[2], ""]
        elif k == "p":
            out += [b[1], ""]
        elif k == "kv":
            out += [f"- **{a}:** {v}" for a, v in b[1]] + [""]
        elif k == "verdict":
            out += [f"**Veredito: {b[2]}**", ""]
        elif k == "table":
            out.append("| " + " | ".join(_md_cell(h) for h in b[1]) + " |")
            out.append("|" + "---|" * len(b[1]))
            out += ["| " + " | ".join(_md_cell(c) for c in row) + " |" for row in b[2]]
            out.append("")
        elif k == "ul":
            out += [f"- {x}" for x in b[1]] + [""]
        elif k == "img":
            out += [f"![{b[3]}]({b[2]})", "", f"*{b[3]}*", ""]
    return "\n".join(out).rstrip() + "\n"


# ----------------------------------------------------------------------------------------------- HTML
_CSS = """body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1200px;margin:2em auto;
padding:0 1em;color:#1a1a1a;line-height:1.4}table{border-collapse:collapse;margin:.6em 0 1.2em;font-size:.86em;
width:100%}th,td{border:1px solid #ccc;padding:.3em .45em;vertical-align:top;text-align:left}th{background:#f2f2f2}
h1{font-size:1.6em}h2{border-bottom:1px solid #ddd;padding-bottom:.2em;margin-top:1.6em}
.verdict{display:inline-block;padding:.4em .9em;border-radius:4px;font-weight:700;font-size:1.2em}
.v-pronto{background:#d8f0d8}.v-nao_pronto{background:#f6d0d0}.v-insuficiente{background:#fbecc4}
figure{margin:1em 0}figure img{max-width:100%;border:1px solid #ddd}figcaption{font-size:.85em;color:#555}
@media print{body{max-width:none}}"""


def to_html(r: Mapping[str, Any], base: Path | None = None) -> str:
    """HTML autónomo; as figuras ficam embutidas (base64) se ``base`` (pasta do design.json) for dado."""
    e = html.escape
    out = ["<!DOCTYPE html>", '<html lang="pt-PT"><head><meta charset="utf-8">',
           f"<title>{e(r['gate'])} — {e(str(r['design'].get('name')))}</title>", f"<style>{_CSS}</style></head><body>"]
    for b in blocks(r):
        k = b[0]
        if k == "h":
            out.append(f"<h{b[1]}>{e(b[2])}</h{b[1]}>")
        elif k == "p":
            out.append(f"<p>{e(b[1])}</p>")
        elif k == "kv":
            out.append("<ul>" + "".join(f"<li><b>{e(a)}:</b> {e(str(v))}</li>" for a, v in b[1]) + "</ul>")
        elif k == "verdict":
            out.append(f'<p><span class="verdict v-{e(b[1])}">Veredito: {e(b[2])}</span></p>')
        elif k == "table":
            out.append("<table><thead><tr>" + "".join(f"<th>{e(str(h))}</th>" for h in b[1]) + "</tr></thead><tbody>")
            out += ["<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>" for row in b[2]]
            out.append("</tbody></table>")
        elif k == "ul":
            out.append("<ul>" + "".join(f"<li>{e(str(x))}</li>" for x in b[1]) + "</ul>")
        elif k == "img":
            src = b[2]
            if base is not None:
                p = (base / b[1])
                if p.is_file():
                    src = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
            out.append(f'<figure><img src="{e(src)}" alt="{e(b[3])}"><figcaption>{e(b[3])}</figcaption></figure>')
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def pdf_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except Exception:  # noqa: BLE001 — ausente ou sem bibliotecas de sistema
        return False
    return True


def write(r: Mapping[str, Any], out: str | Path, base: Path, pdf: bool = False) -> list[Path]:
    """Escreve ``relatorio_<revisão>.json/.md/.html`` (e ``.pdf`` com ``pdf`` e WeasyPrint) em ``out``; copia as
    figuras para ``out/figuras`` (o Markdown aponta para lá; o HTML leva-as embutidas)."""
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    stem = f"relatorio_{str(r['gate']).lower()}"
    files: list[Path] = []
    if r["figures"]:
        fd = o / "figuras"
        fd.mkdir(exist_ok=True)
        for fg in r["figures"]:
            src = base / fg["path"]
            if src.is_file():
                shutil.copyfile(src, fd / src.name)
    pj = o / f"{stem}.json"
    pj.write_text(json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    pm = o / f"{stem}.md"
    pm.write_text(to_markdown(r), encoding="utf-8")
    ph = o / f"{stem}.html"
    h = to_html(r, base)
    ph.write_text(h, encoding="utf-8")
    files += [pj, pm, ph]
    if pdf:
        if not pdf_available():
            raise RuntimeError("PDF pedido mas o WeasyPrint (BSD-3-Clause) não está instalado: "
                               "pip install weasyprint (ou imprima o HTML para PDF no navegador)")
        import weasyprint

        pp = o / f"{stem}.pdf"
        weasyprint.HTML(string=h, base_url=str(o)).write_pdf(str(pp))
        files.append(pp)
    return files


__all__: Sequence[str] = ["blocks", "to_markdown", "to_html", "write", "pdf_available", "num"]
