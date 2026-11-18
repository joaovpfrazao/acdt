"""Small cited reference database for manufacturing and cost (Phase 7).

Policy (AGENTS.md): materials, components, prices and process data are **inputs with provenance**; an AI agent
researches current values on the web and passes them in. This module only keeps a *small* set of reference values,
each with its source and retrieval date, used as documented defaults and for validation. Every value here is
transcribed from the cited source; nothing is estimated. Values marked ``range`` keep the published range and the
default picks the stated point of it (documented in ``note``).
"""
from __future__ import annotations

RETRIEVED = "2026-10-28"

# ------------------------------------------------------------------------------------------------ references
REFS: dict[str, dict] = {
    "gutowski1994": {
        "cite": "Gutowski, T.G., Hoult, D., Dillon, G., Neoh, E.T., Muter, S., Kim, E., Tse, M. (1994). Development of "
                "a theoretical cost model for advanced composite fabrication. Composites Manufacturing 5(4):231-239",
        "url": "https://doi.org/10.1016/0956-7143(94)90138-4"},
    "bao_samareh2000": {
        "cite": "Bao, H.P., Samareh, J.A. (2000). Affordable design: a methodology to implement process-based "
                "manufacturing cost models into the traditional performance-focused multidisciplinary design "
                "optimization. AIAA-2000-4839, Table 1 (V0, tau relative values) and Table 2 (rates, material, "
                "fasteners); first-order process velocity (FOPV) hyperbolic model t = sqrt((L/V0)^2 + 2 tau L/V0)",
        "url": "https://ntrs.nasa.gov/api/citations/20020065232/downloads/20020065232.pdf", "retrieved": RETRIEVED},
    "bao2002": {
        "cite": "Bao, H.P. (2002). Process Cost Modeling for Multi-Disciplinary Design Optimization. Final report, NASA "
                "grant NAG-1-2195 (ODU), Table 4.1 'V0 and tau values for generic wing' (eq. 3.3)",
        "url": "https://ntrs.nasa.gov/api/citations/20020065232/downloads/20020065232.pdf", "retrieved": RETRIEVED},
    "accem_hagnell2016": {
        "cite": "Hagnell, M.K., Akermo, M. (2016). Review of cost estimation: methods and models for aerospace composite "
                "manufacturing. Adv. Manuf.: Polymer & Composites Sci. 2(1):1-11, eq. (1) quoting the Northrop ACCEM "
                "(Advanced Composite Cost Estimating Manual, AFFDL-TR-76-87, 1976): lay-up of woven fabric "
                "t[h] = 0.000851 * area[in^2]^0.6295",
        "url": "https://doi.org/10.1080/20550340.2016.1154642", "retrieved": RETRIEVED},
    "airbus2018_b2f": {
        "cite": "Airbus (2018-04). Metals and composites: finding the right material for each application — 'only "
                "10-20 percent of what we buy ends up in use on an aircraft' (subtractive metal parts)",
        "url": "https://www.airbus.com/en/newsroom/stories/2018-04-metals-and-composites-finding-the-right-material-"
               "for-each-application", "retrieved": RETRIEVED},
    "daher_nesting": {
        "cite": "Alma CAM / DAHER-Socata (Tarbes) case study: routed aluminium sheet parts, automatic nesting reduced "
                "offcuts from 65 % to 50 %",
        "url": "https://www.casestudies.com/company/alma-cam/case-study/intelligent-nesting-software-for-routing-"
               "socatas-aluminium-parts", "retrieved": RETRIEVED},
    "gonzalo2023_b2f": {
        "cite": "Gonzalo et al. (2023). Automated recycling of unidirectional preimpregnated carbon fibre scraps "
                "(Scipedia), citing Blanco et al. (MATCOMP 2018): aeronautical composite parts buy-to-fly 1.1-1.4, "
                "scrap up to 30 %",
        "url": "https://www.scipedia.com/public/Gonzalo_et_al_2023a", "retrieved": RETRIEVED},
    "faa_h_8083_31": {
        "cite": "FAA-H-8083-31 Aviation Maintenance Technician Handbook - Airframe Vol. 1, Ch. 4: rivet pitch 4-6 "
                "rivet diameters (typical), transverse pitch 75 % of pitch, rivet diameter about 3x the thicker sheet; AC 43.13-1B par. 4-57: minimum edge "
                "distance 2D, minimum pitch 3D (single row) / 4D (multi-row)",
        "url": "https://www.faa.gov/documentlibrary/media/advisory_circular/ac_43.13-1b_w-chg1.pdf",
        "retrieved": RETRIEVED},
    "abbott_mil17": {
        "cite": "Abbott, R. (2019). Analysis and Design of Composite and Metallic Flight Vehicle Structures, 3rd ed., "
                "Sec. 4.1.8 (after MIL-HDBK-17F Vol. 3 Sec. 9.3): ply drop-offs >= 20:1 in the load direction, <= 2 "
                "plies per termination; do not buck rivets in composite laminate; fastener edge distance >= 3.0D "
                "(2.5D off-axis) in composites",
        "url": "https://www.abbottaerospace.com/aa-sb-001/4-materials/4-1-composite-materials/4-1-8-general-laminate-"
               "design-guidelines/", "retrieved": RETRIEVED},
    "nasa_learning": {
        "cite": "NASA JSC Cost Estimating — Learning Curve Calculator (Wright cumulative-average and Crawford unit "
                "theories; aerospace 85 %)",
        "url": "https://web.archive.org/web/20120830021941/http://cost.jsc.nasa.gov/learn.html", "retrieved": RETRIEVED},
    "wright1936": {"cite": "Wright, T.P. (1936). Factors affecting the cost of airplanes. J. Aeronautical Sciences "
                           "3(4):122-128 (cumulative-average learning curve)"},
    "crawford1944": {"cite": "Crawford, J.R. (1944). Learning curve, ship curve, ratios, related data. Lockheed "
                             "Aircraft Corp. (unit learning curve)"},
    "raymer_dapca": {
        "cite": "Raymer, D.P. (2018). Aircraft Design: A Conceptual Approach, 6th ed., AIAA, Ch. 18 (DAPCA IV, "
                "constant 2012 USD): H_E = 4.86 We^0.777 V^0.894 Q^0.163, H_T = 5.99 We^0.777 V^0.696 Q^0.263, "
                "H_M = 7.37 We^0.820 V^0.484 Q^0.641, H_Q = 0.076 H_M (cargo) / 0.133 H_M; C_D = 91.3 We^0.630 "
                "V^1.3; C_F = 2498 We^0.325 V^0.822 FTA^1.21; C_M = 22.1 We^0.921 V^0.621 Q^0.799; C_eng = 3112 "
                "(0.043 T_max + 243.25 M_max + 0.969 T_t4 - 2228); wrap rates R_E 115, R_T 118, R_Q 108, R_M 98 USD/h. "
                "Cross-checked against Ozgen (METU AE452 'Cost of an airplane', 2016) and the SI form of the same "
                "equations (5.18/7.22/10.5/67.4/1947/31.2 in kg, km/h)",
        "url": "http://ae.metu.edu.tr/~ae452/cost.pdf", "retrieved": RETRIEVED},
    "gudmundsson2014": {
        "cite": "Gudmundsson, S. (2014). General Aviation Aircraft Design: Applied Methods and Procedures, Elsevier, "
                "Ch. 2 (modified Eastlake model, 2012 USD; labour cost = 2.0969 H R CPI; R_ENG 92, R_TOOL 61, R_MFG 53 "
                "USD/h; avionics 15000 USD; piston engine 174 P_BHP; constant-speed propeller 209.66 N D^2 (P/D)^0.12)",
        "url": "https://computationaldesignlab.github.io/aircraft-design/cost/unit_cost.html", "retrieved": RETRIEVED},
    "mihara_rwth2025": {
        "cite": "RWTH Aachen publications record 1019058: Development of a generalized eVTOL vehicle cost model for Urban Air Mobility "
                "operations (DAPCA IV / Eastlake with Gudmundsson 2014 factors): manufacturing F_COMP = 1 + 0.25 "
                "f_comp, QC = 0.13 C_MFG",
        "url": "https://publications.rwth-aachen.de/record/1019058/files/1019058.pdf", "retrieved": RETRIEVED},
    "aace_18r97": {"cite": "AACE International (2020). Recommended Practice 18R-97: Cost Estimate Classification "
                           "System - as applied in engineering, procurement and construction for the process "
                           "industries, Table 1 (expected accuracy ranges at 80 % confidence: Class 5 L -20..-50 % "
                           "H +30..+100 %; Class 4 L -15..-30 % H +20..+50 %; Class 3 L -10..-20 % H +10..+30 %; "
                           "Class 2 L -5..-15 % H +5..+20 %; Class 1 L -3..-10 % H +3..+15 %); generic "
                           "principles in RP 17R-97. Ranges widen with technological complexity and weak "
                           "reference data",
                   "url": "https://web.aacei.org/docs/default-source/toc/toc_18r-97.pdf", "retrieved": "2026-10-28"},
    "bls_cpi": {
        "cite": "U.S. Bureau of Labor Statistics, CPI-U, U.S. city average, all items (CUUR0000SA0), annual averages",
        "url": "https://data.bls.gov/timeseries/CUUR0000SA0", "retrieved": RETRIEVED},
    "gama2024": {
        "cite": "GAMA (2025-02-26). 2024 Year-End General Aviation Airplane Shipment Report: CE-172S Skyhawk SP "
                "deliveries 31/41/48/44 by quarter = 164",
        "url": "https://gama.aero/wp-content/uploads/2024ShipmentReport_2025-02-26.pdf", "retrieved": RETRIEVED},
    "flieger2025_c172": {
        "cite": "fliegermagazin (2025-05-05), T. Borchert, 'Wie früher: Mein Flug in der neuen Cessna 172 Skyhawk': "
                "base price of the current Skyhawk 499,000 USD; 180 Skyhawks sold in 2023; Lycoming IO-360 180 hp",
        "url": "https://www.fliegermagazin.de/flugzeuge/wie-frueher-mein-flug-in-der-neuen-cessna-172-skyhawk/",
        "retrieved": RETRIEVED},
}

# ------------------------------------------------------------------------------------------------ cost indices
# CPI-U annual averages (1982-84 = 100). 2012 is the base year of DAPCA IV (Raymer 6th ed.) and of Gudmundsson.
CPI_U = {1986: 109.6, 2000: 172.2, 2012: 229.594, 2024: 313.689, 2025: 321.943,
         2026: 336.940}  # 2026 = September 2026 monthly index (latest at retrieval), not an annual average
CPI_SOURCE = "bls_cpi"


def cpi_factor(to_year: int, from_year: int = 2012, table: dict | None = None) -> float:
    """Escalation factor CPI(to)/CPI(from) from the CPI-U table (or a user table {year: index})."""
    t = {**CPI_U, **(table or {})}
    if to_year not in t or from_year not in t:
        raise KeyError(f"CPI for {from_year}/{to_year} not in table — pass cpi_table={{year: index}} "
                       "(BLS CUUR0000SA0 annual average) with its source")
    return t[to_year] / t[from_year]


# ------------------------------------------------------------------------------------------------ process data
# FOPV (first-order process velocity) parameters. Units: V0 [in^2/min] (or in/min for assembly), tau [min];
# extensive variable: wetted area A [in^2] for fabrication, perimeter B [in] for assembly (Bao & Samareh 2000).
# Absolute values: Bao (2002) Table 4.1 (= base spar V0 2.4624, tau 3.6934e4 x Table-1 relative values).
FOPV = {
    ("metal", "skin"): (3.024, 3.1123e4), ("metal", "rib"): (2.059, 4.1423e4),
    ("metal", "spar"): (2.4624, 3.6934e4), ("metal", "assembly"): (0.0395, 2.1341e4),
    ("composite", "skin"): (2.1447, 4.3883e4), ("composite", "rib"): (0.8236, 1.0356e4),
    ("composite", "spar"): (1.4485, 6.2788e4), ("composite", "assembly"): (0.02826, 2.9877e4),
}
FOPV_SOURCE = "bao2002"
FOPV_NOTE = ("Industry estimates (2000) for a generic transport-type wing: aluminium parts milled, composite parts "
             "lay-up or RTM; recurring time only, set-up and delay excluded (Bao & Samareh 2000 Table 2)")
FOPV_RATE_USD_H = (60.0, 2000)          # labour rate used with these times (Bao & Samareh 2000 Table 2), USD of 2000
FASTENER_USD = (0.20, 2000)             # per fastener (Bao & Samareh 2000 Table 2)

# ACCEM woven-fabric lay-up (per ply): t[h] = a * area[in^2]^b
ACCEM_WOVEN_LAYUP = (0.000851, 0.6295)

# buy-to-fly ratios (mass bought / mass flown)
BUY_TO_FLY = {
    "cnc_machining": {"range": (1 / 0.20, 1 / 0.10), "default": 1 / 0.15, "source": "airbus2018_b2f",
                      "note": "subtractive metal parts: 10-20 % of the bought metal flies; default = mid-range 15 %"},
    "sheet_metal_riveted": {"range": (1 / 0.50, 1 / 0.35), "default": 1 / 0.50, "source": "daher_nesting",
                            "note": "routed Al sheet parts: offcuts 65 % (manual nesting) -> 50 % (automatic); "
                                    "default = automatic nesting"},
    "composite": {"range": (1.1, 1.4), "default": 1.4, "source": "gonzalo2023_b2f",
                  "note": "aeronautical composite parts 1.1-1.4; default = upper value (manual lay-up scrap)"},
}

RIVET_RULES = {"D_over_t": 3.0, "pitch_D": (4.0, 6.0), "transverse_pitch_of_pitch": 0.75, "edge_min_D": 2.0, "pitch_min_D": 3.0,
               "source": "faa_h_8083_31"}
COMPOSITE_RULES = {"ply_drop_min_ratio": 20.0, "max_plies_per_drop": 2, "fastener_edge_min_D": 3.0,
                   "no_bucked_rivets": True, "source": "abbott_mil17"}

LEARNING_DEFAULT = {"slope": 0.85, "source": "nasa_learning", "note": "aerospace 85 % (NASA JSC calculator)"}


def ref(key: str) -> str:
    r = REFS[key]
    s = r["cite"]
    if r.get("url"):
        s += f" <{r['url']}>"
    if r.get("retrieved"):
        s += f" (retrieved {r['retrieved']})"
    return s
