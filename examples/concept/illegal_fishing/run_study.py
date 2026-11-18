"""Worked example of the AI concept trade: "quero vigiar esta área de mar porque há barcos estrangeiros a fazer
pesca ilegal".

This script is the transcript of the decisions taken by the agent (acting as the designer) with the concept tools
only (the same functions the MCP server exposes). Every number is a tool result, a researched value with source,
or a PRESSUPOSTO with rationale. Run from the repo root:

    python examples/concept/illegal_fishing/run_study.py

Output: examples/output/concept/illegal_fishing/{study.json, report.md, pareto.png}
Check determinism: acdt concept replay examples/output/concept/illegal_fishing/study.json --with-sizing
"""
from __future__ import annotations

import math
import shutil
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from acdt.ai import concept as C  # noqa: E402

HERE = Path("examples/concept/illegal_fishing")
OUT = Path("examples/output/concept/illegal_fishing")
RETR = "2026-10-29"
KN = 0.514444                                            # m/s per knot (exact: 1852/3600)

if OUT.exists():
    shutil.rmtree(OUT)
s = C.study_start("Vigilância de pesca ilegal na ZEE continental (zona centro)",
                  "Quero vigiar esta área de mar porque há barcos estrangeiros a fazer pesca ilegal.",
                  output_dir=str(OUT))
sid = s["study_id"]


def add(kind, content):
    return C.study_add(sid, kind, content)


# ------------------------------------------------------------------ 1. understanding, assumptions, questions
add("interpretation", "Necessidade: detetar, seguir e identificar (para prova e intervenção) embarcações de pesca "
    "estrangeiras a pescar ilegalmente numa área de mar português. A decisão a tomar é QUE ARQUITETURA de "
    "sistema aéreo não tripulado (quantas aeronaves, de que tamanho, com que sensores, a partir de onde) dá "
    "cobertura credível ao menor custo. A intervenção (abordagem) é de outra entidade (Marinha/autoridade de "
    "pescas); o sistema aéreo entrega deteção + identificação + track.")
add("interpretation", "Cadeia de missão: radar marítimo (área larga, dia/noite, independente do AIS — quem pesca "
    "ilegalmente pode desligar o AIS) → correlação com AIS/VMS → EO/IR para identificação (nome/número de casco, "
    "artes de pesca) → registo e entrega do track. Logo, os requisitos-chave são probabilidade de deteção na "
    "área numa janela de tempo, presença permanente e capacidade de identificação.")
add("assumption", {"text": "Área de vigilância: retângulo 38.9–40.1 N × 10.9–9.7 W (ao largo de Peniche/Nazaré, "
                   "dentro da ZEE continental)", "rationale": "o utilizador não indicou a área; escolhida uma "
                   "área representativa (~1/20 da ZEE continental de 287 521 km²) para tornar o estudo concreto"})
add("assumption", {"text": "Base: BA5 Monte Real (39.828 N, 8.887 W), pista existente",
                   "rationale": "aeródromo militar público mais próximo da área; alternativa civil a avaliar"})
add("assumption", {"text": "Alvo: embarcação de pesca 15–40 m; a pescar 2–6 kn (arrasto de fundo 3–5 kn), em "
                   "trânsito 8–12 kn", "source": "FAO / IMCS (velocidades de arrasto e trânsito)"})
add("assumption", {"text": "Janela de deteção = tempo de travessia da área por uma embarcação a 10 kn",
                   "rationale": "pior caso razoável: embarca que entra, pesca pouco e sai; uma embarcação a pescar "
                   "fica muitas horas (janela maior, requisito mais fácil) — sensibilidade a 12 h"})
add("assumption", {"text": "Disponibilidade operacional da aeronave A = 0.85 (sensibilidade 0.70)",
                   "rationale": "sem dado público fiável para esta classe; valor de planeamento a confirmar com "
                   "MTBF/MTTR reais — o número de aeronaves é sensível a isto"})
add("assumption", {"text": "Turnaround no solo 4 h (L/M), reserva 1 h, sobreposição na passagem de estação 0.25 h",
                   "rationale": "abastecimento, inspeção pós-voo e briefing; reserva para desvio/meteo"})
add("assumption", {"text": "Largura de varrimento do radar: NSP-7 = 20.4 km (datasheet, alvo 'fishing boat'); "
                   "NSP-2 = 10 km (sensibilidade 5–20 km)", "rationale": "NSP-2 anuncia 44 km de deteção MMTI "
                   "marítima sem indicar a classe de alvo; 10 km é deliberadamente conservador"})
add("assumption", {"text": "Lei de deteção de Koopman (pesquisa aleatória) para o requisito",
                   "rationale": "conservador face ao varrimento paralelo (alvo em movimento, navegação imperfeita, "
                   "estado do mar); o varrimento paralelo dá o limite otimista"})
add("assumption", {"text": "Produção de N = 50 unidades para o CER de custo (L0); ano 2026",
                   "rationale": "ordem de grandeza de um programa pequeno; o custo unitário é sensível a N e o CER "
                   "tem baixa confiança para UAV"})
for q in ["Qual é a área real (polígono) e há várias áreas/prioridades?",
          "É preciso presença 24/7 ou só em certos períodos/épocas (ex.: campanhas de pesca, noite)?",
          "Que meios já existem (navios-patrulha, aviões de patrulha marítima, dados de satélite EMSA/Copernicus) "
          "e com quem o sistema tem de partilhar dados?",
          "Orçamento de aquisição e de operação, e horizonte do programa?",
          "Bases possíveis (BA5, aeródromos civis, navios) e restrições de espaço aéreo?"]:
    add("question", q)
for t, u in [("IMSAR NSP-7: 10.9 kg, 275 W, banda Ku; marítimo: faixa 20.4 km para barco de pesca",
              "https://www.radartutorial.eu/19.kartei/08.airborne/pubs/nsp-7_datasheet_spreads.pdf"),
             ("IMSAR NSP-2: 1.5–2.1 kg, ≤ 56 W; MMTI marítimo deteção/track 44 km (classe não indicada)",
              "https://www.imsar.com/radar-products/nsp-2"),
             ("Trillium HD25 0.35–0.39 kg; HD45-LV-CZ 1.35 kg", "https://www.trilliumeng.com"),
             ("ZEE de Portugal continental 287 521 km²", "https://www.dgrm.pt"),
             ("Velocidades de arrasto 2–6 kn, trânsito 8–12 kn", "FAO fishing techniques / IMCS network"),
             ("Gasolina 95 em Portugal: 2.067 €/L (média DGEG, 27 out 2026)", "https://www.combustivel.com.pt")]:
    add("source", {"text": t, "url": u, "retrieved": RETR})

# ------------------------------------------------------------------ 2. geometry and measurable requirements
area_poly = [[38.9, -10.9], [38.9, -9.7], [40.1, -9.7], [40.1, -10.9]]
g = C.geo_measure(points={"BA5": [39.828, -8.887], "centro": [39.5, -10.3], "bordo_E": [39.5, -9.7],
                          "bordo_W": [39.5, -10.9]},
                  legs=[["BA5", "centro"], ["BA5", "bordo_E"], ["bordo_W", "bordo_E"]],
                  polygon=area_poly, study_id=sid)
A_km2 = g["area_km2"]
legs = {f"{l['from']}-{l['to']}": l["distance_km"] for l in g["legs"]}
d_base = legs["BA5-centro"]
width = legs["bordo_W-bordo_E"]
cross = C.transit_time(distance_km=width, airspeed_m_s=10 * KN, study_id=sid)
T_win = cross["t_out_h"]
add("requirement", {"id": "REQ1", "text": "Detetar uma embarcação de pesca na área dentro da janela de travessia",
                    "metric": "pod_window", "threshold": ">= 0.9",
                    "justification": f"janela = {T_win:.2f} h (travessia de {width:.0f} km a 10 kn, chamada "
                                     f"transit_time); 0.9 = PRESSUPOSTO de eficácia credível"})
add("requirement", {"id": "REQ2", "text": "Presença permanente (24/7) dos sensores previstos na estação",
                    "metric": "p_enough_available", "threshold": ">= 0.95",
                    "justification": "prob. de haver aeronaves disponíveis suficientes para manter o ciclo "
                                     "(binomial k-de-N); 0.95 = PRESSUPOSTO"})
jr = C.johnson_range(target_dim_m=15.0, task="identification", ifov_rad=1.0e-4, study_id=sid)
add("requirement", {"id": "REQ3", "text": "Identificação EO/IR de uma embarcação de 15 m a distância de segurança",
                    "metric": "ifov_rad", "threshold": "<= 1e-4 (≈ 11.7 km a 50 %)",
                    "justification": f"Johnson (identificação, 6.4 ciclos): IFOV 0.1 mrad → "
                                     f"{jr['max_range_km']:.1f} km; o datasheet da HD45 tem de ser verificado "
                                     f"contra este valor (não avaliado aqui)"})
add("requirement", {"id": "REQ4", "text": "Minimizar o custo de aquisição da frota (e, como indicador de operação, "
                    "horas de voo e combustível por dia)", "metric": "acquisition_usd", "threshold": "min",
                    "justification": "objetivo, não limite (orçamento desconhecido — pergunta Q4)"})
h_L = C.radar_horizon(h_sensor_m=3000, h_target_m=5, study_id=sid)
h_S = C.radar_horizon(h_sensor_m=600, h_target_m=5, study_id=sid)
add("finding", f"Horizonte radar a 3000 m = {h_L['horizon_km']:.0f} km e a 600 m = {h_S['horizon_km']:.0f} km, "
    f"muito acima dos alcances dos radares (20–44 km): a deteção é limitada pelo sensor, não pelo horizonte; "
    f"voar mais baixo não penaliza a deteção mas reduz a área por hora apenas pela velocidade.")

# ------------------------------------------------------------------ 3. alternatives (incl. non-evaluable)
alts_txt = {
    "A1": ("1×L, sem continuidade (uma aeronave grande)", True, "size_fleet + persistent_coverage(fleet 1)"),
    "A2": ("L, 1 estação 24/7", True, "persistent_coverage + sweep_coverage + size_fleet"),
    "A3": ("L, 2 estações 24/7", True, "idem"),
    "A4": ("M, 2 estações 24/7 (radar ligeiro)", True, "idem"),
    "A5": ("M, 3 estações 24/7", True, "idem"),
    "A6": ("Misto: 1 estação L (área larga) + 1 estação M (identificação/seguimento por cueing)", True,
           "idem; POD combinada pela aditividade do esforço de Koopman"),
    "A7": ("S elétrico 25 kg lançado de navio, 2 estações", True, "trânsito ~0; custo do navio NÃO incluído"),
}
for k, (t, ev, how) in alts_txt.items():
    add("alternative", {"id": k, "text": t, "evaluable": ev, "how": how})
for k, t, why in [
    ("X1", "Aeróstato cativo costeiro com radar", "acdt não dimensiona aeróstatos; cobre só a faixa costeira "
     "(a área começa ~25 km da costa)"),
    ("X2", "Satélite SAR + AIS (ex.: serviços EMSA/Copernicus) com aeronave só para identificação",
     "revisita e latência de satélite não modeladas; muito promissor como cueing — pergunta Q3"),
    ("X3", "Avião tripulado de patrulha marítima existente", "meio existente, custo/hora não público aqui"),
    ("X4", "VTOL lançado de navio-patrulha", "acdt ainda não dimensiona VTOL"),
    ("X5", "HALE solar / estratosférico", "fora do âmbito do dimensionamento atual"),
    ("X6", "Veículos de superfície não tripulados (USV) com radar", "não é aeronave; horizonte baixo")]:
    add("alternative", {"id": k, "text": t, "evaluable": False, "reason": why})

# ------------------------------------------------------------------ 4. size one aircraft of each type
specs = {v: str(HERE / f"variant_{v}.yaml") for v in "LMS"}
base = C.size_fleet(variants=[{"id": v, "spec_path": specs[v], "quantity": 1, "cost": {"N": 50, "year": 2026},
                               "safety": {}} for v in "LMS"], study_id=sid)
ac = {v["id"]: v for v in base["variants"]}
for v in "LMS":
    a = ac[v]
    add("finding", f"Variante {v}: W0 {a['aircraft']['W0_kg']:.1f} kg, endurance {a['aircraft']['endurance_h']:.2f} h, "
        f"custo unitário {a['cost']['unit_cost_usd']/1e3:.0f} k$ (N=50), perda por surtida "
        f"{a['safety']['p_loss_per_sortie']:.4f}; viável={a['feasible']}; verificações falhadas: "
        f"{', '.join(a['failed_checks']) or 'nenhuma'}; base de certificação {a['certification']['bases']}.")

W = {"L": 20.4, "M": 10.0, "S": 10.0}
cov = {}
for v, dist, tout in [("L", d_base, None), ("M", d_base, None), ("S", None, 0.25)]:
    a = ac[v]["aircraft"]
    kw = dict(distance_km=dist, airspeed_m_s=a["cruise_speed_m_s"]) if dist else dict(t_out_h=tout, t_back_h=tout)
    turn = 4.0 if v != "S" else 1.0          # S: troca de bateria no navio — PRESSUPOSTO
    reserve = 1.0 if v != "S" else 0.25
    for n_st in (1, 2, 3):
        cov[(v, n_st)] = C.persistent_coverage(endurance_h=a["endurance_h"], turnaround_h=turn, reserve_h=reserve,
                                               handoff_overlap_h=0.25, n_stations=n_st, availability=0.85,
                                               confidence=0.95, study_id=sid, **kw)
add("assumption", {"text": "S: lançamento e recuperação no navio dentro da área (trânsito 0.25 h cada sentido), "
                   "troca de bateria 1 h, reserva 0.25 h", "rationale": "opção criativa 'mothership'; custo e "
                   "disponibilidade do navio não incluídos"})


def pod(v, n_on):
    return C.sweep_coverage(area_km2=A_km2, sweep_width_km=W[v], speed_m_s=ac[v]["aircraft"]["cruise_speed_m_s"],
                            n_on_station=n_on, time_h=T_win, pod_target=0.9, study_id=sid)


def fleet_cost(parts):
    """parts: [(variant, quantity)] → size_fleet with quantities (acquisition from the CER)."""
    return C.size_fleet(variants=[{"id": f"{v}x{q}", "spec_path": specs[v], "quantity": q,
                                   "cost": {"N": 50, "year": 2026}, "safety": {}} for v, q in parts], study_id=sid)


rows = []


def record(aid, parts, pods, p_enough, fh_day, extra=None):
    f = fleet_cost(parts)["fleet"]
    p_miss = math.prod(1 - p["pod_at_time"]["pod_random_search"] for p in pods)   # Koopman effort is additive
    fuel = sum(fh * (ac[v]["aircraft"].get("fuel_kg_per_fh_approx") or 0.0) for v, fh in fh_day)
    m = {"n_aircraft": f["n_aircraft"], "acquisition_usd": f.get("acquisition_usd"),
         "pod_window": 1 - p_miss, "p_enough_available": p_enough,
         "flight_hours_per_day": sum(fh for _, fh in fh_day), "fuel_kg_per_day": fuel}
    m.update(extra or {})
    rows.append({"id": aid, "metrics": m})
    return m


# A1 — one big aircraft (no continuity)
c1 = C.persistent_coverage(endurance_h=ac["L"]["aircraft"]["endurance_h"], turnaround_h=4.0, reserve_h=1.0,
                           handoff_overlap_h=0.25, distance_km=d_base,
                           airspeed_m_s=ac["L"]["aircraft"]["cruise_speed_m_s"], availability=0.85, fleet_size=1,
                           study_id=sid)
record("A1", [("L", 1)], [pod("L", c1["fleet"]["mean_on_station"])], c1["fleet"]["p_enough_available"],
       [("L", c1["fleet"]["mean_on_station"] * 24 * (c1["t_out_h"] + c1["cycle"]["time_on_station_h"]
                                                    + c1["t_back_h"]) / c1["cycle"]["time_on_station_h"])])
for aid, v, n_st in [("A2", "L", 1), ("A3", "L", 2), ("A4", "M", 2), ("A5", "M", 3), ("A7", "S", 2)]:
    c = cov[(v, n_st)]
    n = c["fleet_for_confidence"]["n"]
    pc = C.persistent_coverage(endurance_h=ac[v]["aircraft"]["endurance_h"],
                               turnaround_h=4.0 if v != "S" else 1.0, reserve_h=1.0 if v != "S" else 0.25,
                               handoff_overlap_h=0.25, n_stations=n_st, availability=0.85, fleet_size=n,
                               study_id=sid, **(dict(distance_km=d_base,
                                                     airspeed_m_s=ac[v]["aircraft"]["cruise_speed_m_s"])
                                                if v != "S" else dict(t_out_h=0.25, t_back_h=0.25)))
    record(aid, [(v, n)], [pod(v, n_st)], pc["fleet"]["p_enough_available"], [(v, c["flight_hours_per_day"])],
           {"requires_ship": 1.0} if v == "S" else None)
# A6 — mixed: each type sized for √0.95 so that the joint probability (independent) is ≥ 0.95
cL = C.persistent_coverage(endurance_h=ac["L"]["aircraft"]["endurance_h"], turnaround_h=4.0, reserve_h=1.0,
                           handoff_overlap_h=0.25, distance_km=d_base,
                           airspeed_m_s=ac["L"]["aircraft"]["cruise_speed_m_s"], availability=0.85,
                           confidence=math.sqrt(0.95), study_id=sid)
cM = C.persistent_coverage(endurance_h=ac["M"]["aircraft"]["endurance_h"], turnaround_h=4.0, reserve_h=1.0,
                           handoff_overlap_h=0.25, distance_km=d_base,
                           airspeed_m_s=ac["M"]["aircraft"]["cruise_speed_m_s"], availability=0.85,
                           confidence=math.sqrt(0.95), study_id=sid)
nL, nM = cL["fleet_for_confidence"]["n"], cM["fleet_for_confidence"]["n"]
fL = C.fleet_reliability(n=nL, k=cL["aircraft_needed_in_cycle"], p_success=0.85, study_id=sid)
fM = C.fleet_reliability(n=nM, k=cM["aircraft_needed_in_cycle"], p_success=0.85, study_id=sid)
record("A6", [("L", nL), ("M", nM)], [pod("L", 1), pod("M", 1)], fL["p_at_least_k"] * fM["p_at_least_k"],
       [("L", cL["flight_hours_per_day"]), ("M", cM["flight_hours_per_day"])])

# attrition indicator: expected losses per year = sorties/day · 365 · p_loss_per_sortie (ARP4761 low-fi)
sorties = {"A1": [], "A2": [("L", cov[("L", 1)])], "A3": [("L", cov[("L", 2)])], "A4": [("M", cov[("M", 2)])],
           "A5": [("M", cov[("M", 3)])], "A6": [("L", cL), ("M", cM)], "A7": [("S", cov[("S", 2)])]}
for r in rows:
    r["metrics"]["losses_per_year"] = sum(c["sorties_per_day"] * 365 * ac[v]["safety"]["p_loss_per_sortie"]
                                          for v, c in sorties[r["id"]]) if sorties[r["id"]] else None
add("finding", "Indicadores derivados no script (aritmética sobre resultados das ferramentas): pod_window de "
    "frotas mistas = 1 − Π(1 − POD_i) (aditividade do esforço de Koopman); losses_per_year = surtidas/dia · 365 · "
    "p_loss_per_sortie (ARP4761 low-fi, taxas genéricas do template 'uas'); A6 dimensionada com confiança √0.95 "
    "por tipo (independência).")

# ------------------------------------------------------------------ 5. compare (Pareto, no weights)
show = ["n_aircraft", "acquisition_usd", "pod_window", "p_enough_available", "flight_hours_per_day",
        "fuel_kg_per_day", "losses_per_year"]
res = C.compare(rows, objectives={"acquisition_usd": "min", "pod_window": "max", "flight_hours_per_day": "min"},
                constraints={"pod_window": {"min": 0.9}, "p_enough_available": {"min": 0.95}},
                plot={"x": "acquisition_usd", "y": "pod_window", "file": "pareto.png"},
                title="Arquiteturas — custo de aquisição vs POD na janela (REQ1, REQ2 como restrições)",
                show=show, study_id=sid)

C.compare(rows, objectives={"acquisition_usd": "min", "pod_window": "max"},
          plot={"x": "acquisition_usd", "y": "pod_window", "file": "pareto_sem_restricoes.png"},
          title="Compromisso custo vs POD sem restrições (o que se ganha por cada dólar)", show=show, study_id=sid)
add("finding", "A taxa de perda por surtida vem do template ARP4761 low-fi 'uas' com taxas de falha genéricas: com "
    "dezenas de surtidas por semana, a atrição prevista (losses_per_year) pesa mais do que a aquisição. É o "
    "PRESSUPOSTO mais crítico para o custo de ciclo de vida e tem de ser substituído por dados de fiabilidade "
    "reais (MTBF dos componentes) antes de qualquer decisão.")

# ------------------------------------------------------------------ 6. sensitivities (re-run the drivers)
sens = {}
for Wm in (5.0, 20.0):
    W["M"] = Wm
    sens[f"A4 POD com W_NSP-2={Wm:g} km"] = pod("M", 2)["pod_at_time"]["pod_random_search"]
W["M"] = 10.0
for Ax in (0.70,):
    c = C.persistent_coverage(endurance_h=ac["L"]["aircraft"]["endurance_h"], turnaround_h=4.0, reserve_h=1.0,
                              handoff_overlap_h=0.25, n_stations=2, distance_km=d_base,
                              airspeed_m_s=ac["L"]["aircraft"]["cruise_speed_m_s"], availability=Ax,
                              confidence=0.95, study_id=sid)
    sens[f"A3 frota L para 95 % com A={Ax}"] = c["fleet_for_confidence"]["n"]
sw = C.sweep_coverage(area_km2=A_km2, sweep_width_km=W["L"], speed_m_s=ac["L"]["aircraft"]["cruise_speed_m_s"],
                      n_on_station=1, time_h=12.0, study_id=sid)
sens["A2 POD com janela 12 h"] = sw["pod_at_time"]["pod_random_search"]
sens["A2 POD varrimento paralelo (otimista)"] = pod("L", 1)["pod_at_time"]["pod_parallel_sweep"]
add("finding", "Sensibilidades: " + "; ".join(f"{k} → {v:.3g}" for k, v in sens.items()))

# ------------------------------------------------------------------ 7. recommendation
byid = {r["id"]: r for r in res["rows"]}
feas = [r["id"] for r in res["rows"] if r["feasible"]]
chosen = min((i for i in res["pareto"] if i in feas),
             key=lambda i: next(x["metrics"]["acquisition_usd"] for x in rows if x["id"] == i)) if feas else None
m = next(x["metrics"] for x in rows if x["id"] == chosen) if chosen else {}
add("recommendation", {
    "chosen": chosen,
    "text": (f"{chosen}: {alts_txt[chosen][0]} — {m['n_aircraft']} aeronaves, aquisição ≈ "
             f"{m['acquisition_usd']/1e6:.2f} M$ (CER L0, baixa confiança), POD na janela {m['pod_window']:.2f}, "
             f"P(frota suficiente) {m['p_enough_available']:.3f}, {m['flight_hours_per_day']:.0f} h de voo/dia."
             if chosen else "Nenhuma alternativa cumpre REQ1+REQ2 com os PRESSUPOSTOS atuais."),
    "rationale": "alternativa mais barata no conjunto de Pareto que cumpre REQ1 (POD ≥ 0.9 na janela) e REQ2 "
                 "(P ≥ 0.95); sem pesos — o compromisso custo/POD/horas de voo está no gráfico e na tabela. "
                 "ATENÇÃO: a variante L ainda não fecha no dimensionamento L0 (verificações falhadas: "
                 + ", ".join(ac["L"]["failed_checks"]) + "); a arquitetura é válida ao nível conceptual, a "
                 "aeronave tem de ser corrigida (trim/estabilidade/W&B/trem; a verificação por segmentos dá "
                 "endurance ligeiramente abaixo de 16 h). A atrição prevista (FIN6) domina o custo de ciclo de "
                 "vida se as taxas genéricas se confirmarem.",
    "sensitivities": sens,
    "not_evaluated": "X1–X6 (aeróstato, satélite+aeronave, avião tripulado, VTOL, HALE, USV); custo de operação "
                     "(manutenção, pessoal, seguros); meteorologia e espaço aéreo; desempenho do radar com estado "
                     "do mar; o custo do navio em A7; a câmara (REQ3) contra o datasheet",
    "next_steps": "responder às perguntas Q1–Q5; obter a largura de varrimento do NSP-2 para barco de pesca; "
                  "corrigir as verificações falhadas da variante escolhida (trim/HQ/W&B/trem) em L1; avaliar X2 "
                  "(satélite como cueing) porque pode reduzir muito o número de aeronaves",
})
C.study_report(sid)
print(f"[study] {OUT}/report.md  pareto={res['pareto']} feasible={feas} chosen={chosen}")
for r in rows:
    print(r["id"], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r["metrics"].items()})
