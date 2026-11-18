# Copyright (c) 2026 João Frazão. SPDX-License-Identifier: Apache-2.0
"""Ingestão de dados de ensaio e calibração (acdt.testdata/1, acdt.calib/1; docs/CALIBRACAO.md).

Os dados destes testes são SINTÉTICOS (gerados aqui com fatores verdadeiros conhecidos e semente explícita),
marcados ``synthetic: true``, exceto o caso C172S, que usa só os valores publicados já citados no repositório
(Cessna 172S Information Manual: V_S0 48 KCAS, MTOW 1157 kg, S 16,2 m²)."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from acdt.core import design_db as DDB
from acdt.core.calibration import fitting as F
from acdt.core.calibration import ingest as I
from acdt.core.calibration import record as R

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "calibration"
SYN = {"synthetic": True, "source": "teste: dados sintéticos gerados no próprio teste", "kind": "tunel"}


def _polar(seed: int = 1, n: int = 25, sd: float = 4e-4, CD0: float = 0.025, K: float = 0.045,
           with_sd: bool = True) -> I.Dataset:
    rng = np.random.default_rng(seed)
    cl = np.linspace(0.1, 1.2, n)
    cd = CD0 + K * cl ** 2 + rng.normal(0, sd, n)
    meta = dict(SYN)
    if with_sd:
        meta["channels"] = {"CD": {"uncertainty": {"sd": sd, "source": "σ do ruído sintético"}}}
    return I.from_arrays("polar", {"CL": (cl, "1"), "CD": (cd, "1")}, meta)


STUDY = {"name": "p", "level": "L1", "model": {"expr": "CD0 + K*CL**2", "output": "CD"},
         "parameters": {"CD0": {"initial": 0.03, "bounds": [0, 0.1], "nominal": 0.027}, "K": {"initial": 0.05}},
         "acceptance": {"min_points": 10, "max_rel_sd": 0.1, "max_chi2_red": 3, "allow_synthetic": True}}


def _run(study: dict, ds: I.Dataset) -> dict:
    spec = F.ModelSpec.from_dict(study)
    return R.build_record(study, spec, ds, F.fit(spec, ds))


# ------------------------------------------------------------------------------------------------- ingestão
def test_csv_units_meta_and_uncertainty(tmp_path: Path) -> None:
    f = tmp_path / "d.csv"
    f.write_text("# comentário\nV [kt],alpha_deg,CL,T (degC)\n100,2,0.5,15\n120,,0.4,16\n", encoding="utf-8")
    (tmp_path / "d.csv.meta.yaml").write_text(yaml.safe_dump({
        "synthetic": True, "source": "teste", "kind": "voo", "conditions": {"h_m": "1000 ft"},
        "channels": {"V": {"uncertainty": {"resolution": 1.0, "source": "leitura de 1 kt"}},
                     "CL": {"unit": "1", "uncertainty": {"half_width": 0.03, "source": "x"}}}}), encoding="utf-8")
    ds = I.load(f)
    assert ds.channels["V"].unit == "kt" and "alpha_deg" in ds.channels
    assert ds.channels["alpha_deg"].unit == "deg"
    assert np.isnan(ds.channels["alpha_deg"].values[1])  # célula vazia = em falta, nunca zero
    assert ds.channels["CL"].unit == "1"
    assert ds.channels["T"].unit == "degC"
    np.testing.assert_allclose(ds.channels["V"].to("m/s"), [100 * 0.514444, 120 * 0.514444], rtol=1e-5)
    np.testing.assert_allclose(ds.channels["T"].to("K"), [288.15, 289.15])  # conversão afim
    assert ds.channels["V"].uncertainty["sd"] == pytest.approx(1 / (2 * math.sqrt(3)))  # GUM F.2.2.1
    assert ds.channels["CL"].uncertainty["sd"] == pytest.approx(0.03 / math.sqrt(3))  # GUM 4.3.7
    np.testing.assert_allclose(ds.channels["V"].sd_to("m/s"), 0.514444 / (2 * math.sqrt(3)), rtol=1e-5)
    assert ds.meta["conditions"]["h_m"] == pytest.approx(304.8)
    assert ds.meta["date"] is None and ds.synthetic
    assert len(ds.file["sha256"]) == 64
    assert ds.to_dict()["schema"] == "acdt.testdata/1"


def test_meta_required_and_errors(tmp_path: Path) -> None:
    f = tmp_path / "d.csv"
    f.write_text("a [m],b\n1,2\n", encoding="utf-8")
    with pytest.raises(I.IngestError, match="source"):
        I.load(f)
    with pytest.raises(I.IngestError, match="source"):
        I.load(f, {"synthetic": True})
    with pytest.raises(I.IngestError, match="dimensões"):
        I.load(f, {"source": "x", "channels": {"a": {"unit": "kg"}}})
    with pytest.raises(I.IngestError, match="sem 'source'"):
        I.load(f, {"source": "x", "channels": {"a": {"uncertainty": {"sd": 1}}}})
    ds = I.load(f, {"source": "relatório X", "channels": {"a": {"unit": "mm"}}})
    assert ds.channels["a"].values[0] == pytest.approx(1000.0) and ds.channels["a"].unit == "mm"
    assert ds.channels["b"].unit is None  # não declarada ≠ adimensional
    with pytest.raises(I.IngestError, match="não declarada"):
        ds.channels["b"].to("1")
    b = tmp_path / "log.bin"
    b.write_bytes(b"\x00")
    with pytest.raises(I.IngestError, match="LGPL"):
        I.load(b, {"source": "x"})


def test_parquet_roundtrip(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    f = tmp_path / "d.parquet"
    pd.DataFrame({"V_m_s": [20.0, 25.0], "CL [1]": [0.8, 0.5], "nota": ["a", "b"]}).to_parquet(f)
    ds = I.load(f, SYN)
    assert ds.fmt == "parquet" and ds.channels["V_m_s"].unit == "m/s" and ds.channels["CL"].unit == "1"
    assert "nota" not in ds.channels


def _write_ulog(path: Path) -> None:
    """ULog mínimo segundo a especificação do formato (docs.px4.io, «ULog File Format»): cabeçalho, B, F, A, D."""
    b = bytearray(b"ULog\x01\x12\x35" + bytes([1]) + struct.pack("<Q", 0))

    def msg(t: str, payload: bytes) -> None:
        b.extend(struct.pack("<HB", len(payload), ord(t)) + payload)
    msg("B", bytes(16) + struct.pack("<QQQ", 0, 0, 0))
    msg("F", b"airspeed:uint64_t timestamp;float true_airspeed_m_s;float temp;")
    msg("A", struct.pack("<BH", 0, 1) + b"airspeed")
    for i in range(5):
        msg("D", struct.pack("<H", 1) + struct.pack("<Qff", 1000 * i, 20.0 + i, 15.0))
    path.write_bytes(bytes(b))


def test_ulog_px4(tmp_path: Path) -> None:
    pytest.importorskip("pyulog")
    f = tmp_path / "voo.ulg"
    _write_ulog(f)
    ds = I.load(f, dict(SYN, kind="voo"))
    assert ds.fmt == "ulog"
    assert ds.channels["airspeed.timestamp"].unit == "us"
    assert ds.channels["airspeed.true_airspeed_m_s"].unit == "m/s"
    assert ds.channels["airspeed.temp"].unit is None
    np.testing.assert_allclose(ds.channels["airspeed.timestamp"].to("s"), [0, 1e-3, 2e-3, 3e-3, 4e-3])


# ------------------------------------------------------------------------------------------------ ajuste WLS
def test_wls_recovers_true_factors_within_uncertainty() -> None:
    rec = _run(STUDY, _polar())
    for k, truth in (("CD0", 0.025), ("K", 0.045)):
        p = rec["parameters"][k]
        assert abs(p["value"] - truth) < 3 * p["sd"]
        assert p["ci95"][0] < truth < p["ci95"][1]
    assert rec["fit"]["dof"] == 23 and rec["method"]["sigma_source"] == "instrumento"
    assert rec["decision"] == "aplicar" and rec["synthetic"]
    assert len(rec["residuals"]) == 25 and "residual_norm" in rec["residuals"][0]
    assert rec["validity"]["ranges"]["CL"] == pytest.approx([0.1, 1.2])


def test_wls_coverage_of_95pct_interval() -> None:
    """Cobertura empírica do IC 95 % em 200 réplicas sintéticas (fatores verdadeiros conhecidos)."""
    spec = F.ModelSpec.from_dict(STUDY)
    hits = 0
    for s in range(200):
        r = F.fit(spec, _polar(seed=100 + s, n=15))
        ci = r.ci95()
        assert ci is not None
        hits += int(ci[1, 0] <= 0.045 <= ci[1, 1])
    assert 0.88 <= hits / 200 <= 0.99


def test_sigma_from_residuals_and_birge() -> None:
    rec = _run(STUDY, _polar(with_sd=False))
    assert rec["method"]["sigma_source"] == "residuos" and rec["fit"]["chi2_red"] is None
    assert abs(rec["parameters"]["K"]["value"] - 0.045) < 3 * rec["parameters"]["K"]["sd"]
    # σ declarado 4× menor do que o ruído real: Birge alarga a covariância
    rng = np.random.default_rng(3)
    cl = np.linspace(0.1, 1.2, 30)
    cd = 0.025 + 0.045 * cl ** 2 + rng.normal(0, 4e-4, cl.size)
    ds = I.from_arrays("p", {"CL": (cl, "1"), "CD": (cd, "1")},
                       dict(SYN, channels={"CD": {"uncertainty": {"sd": 1e-4, "source": "subestimado"}}}))
    rec = _run(STUDY, ds)
    assert rec["fit"]["birge_factor"] and rec["fit"]["birge_factor"] > 4
    assert any(c["criterion"] == "max_chi2_red" and c["status"] == "falha" for c in rec["criteria"])
    assert rec["decision"] == "nao_aplicar"


def test_unknown_uncertainty_never_zero() -> None:
    ds = I.from_arrays("p", {"CL": ([0.5, 0.8], "1"), "CD": ([0.03, 0.04], "1")}, SYN)
    rec = _run(STUDY, ds)  # n = p = 2
    assert rec["fit"]["dof"] == 0
    for p in rec["parameters"].values():
        assert p["sd"] is None and p["ci95"] is None and p["decision"] == "nao_aplicar"
        assert "incerteza do parâmetro desconhecida" in p["reasons"]
    # não identificável: dois parâmetros que só aparecem como produto
    st = dict(STUDY, model={"expr": "a*b*CL**2", "output": "CD"},
              parameters={"a": {"initial": 1.0}, "b": {"initial": 0.05}})
    rec = _run(st, _polar())
    assert rec["fit"]["identifiable"] is False and rec["decision"] == "nao_aplicar"


def test_decision_gates() -> None:
    ds = _polar()
    rec = _run(dict(STUDY, acceptance={}), ds)
    assert rec["decision"] == "nao_aplicar"
    assert all("sem critérios de aceitação declarados" in p["reasons"] for p in rec["parameters"].values())
    rec = _run(dict(STUDY, acceptance={"min_points": 5}), ds)  # sintético sem allow_synthetic
    assert rec["decision"] == "nao_aplicar" and any("sintéticos" in r for r in rec["parameters"]["K"]["reasons"])
    rec = _run(dict(STUDY, acceptance={"min_points": 5, "band": {"K": [0.05, 0.1]}, "allow_synthetic": True}), ds)
    assert rec["parameters"]["K"]["decision"] == "nao_aplicar" and rec["parameters"]["CD0"]["decision"] == "aplicar"
    assert rec["decision"] == "parcial"
    with pytest.raises(F.CalibrationError, match="desconhecidos"):
        _run(dict(STUDY, acceptance={"tolerancia_magica": 1}), ds)


def test_effective_variance_with_input_uncertainty() -> None:
    rng = np.random.default_rng(7)
    cl_true = np.linspace(0.1, 1.2, 40)
    cl = cl_true + rng.normal(0, 0.01, cl_true.size)
    cd = 0.025 + 0.045 * cl_true ** 2 + rng.normal(0, 2e-4, cl_true.size)
    ds = I.from_arrays("p", {"CL": (cl, "1"), "CD": (cd, "1")}, dict(SYN, channels={
        "CD": {"uncertainty": {"sd": 2e-4, "source": "s"}}, "CL": {"uncertainty": {"sd": 0.01, "source": "s"}}}))
    rec = _run(STUDY, ds)
    assert any("Orear" in n for n in rec["method"]["notes"])
    assert rec["fit"]["chi2_red"] < 2.0  # sem a variância efetiva χ²/ν seria ≫ 1
    assert abs(rec["parameters"]["K"]["value"] - 0.045) < 3 * rec["parameters"]["K"]["sd"]


# ------------------------------------------------------------------------------------------------- KOH
def test_koh_requires_priors_and_learns_discrepancy() -> None:
    ds = _polar()
    with pytest.raises(F.CalibrationError, match="prior"):
        _run(dict(STUDY, method="koh"), ds)
    # discrepância de forma do modelo (lomba suave em CL) que o modelo parabólico não tem
    rng = np.random.default_rng(11)
    cl = np.linspace(0.1, 1.2, 30)
    bump = 0.002 * np.exp(-0.5 * ((cl - 0.7) / 0.15) ** 2)
    cd = 0.025 + 0.045 * cl ** 2 + bump + rng.normal(0, 2e-4, cl.size)
    ds = I.from_arrays("p", {"CL": (cl, "1"), "CD": (cd, "1")},
                       dict(SYN, channels={"CD": {"uncertainty": {"sd": 2e-4, "source": "s"}}}))
    st = dict(STUDY, method="koh", discrepancy={"inputs": ["CL"]},
              parameters={"CD0": {"initial": 0.025, "prior": {"mean": 0.025, "sd": 0.002, "source": "teste"}},
                          "K": {"initial": 0.045, "prior": {"mean": 0.046, "sd": 0.004, "source": "teste"}}},
              acceptance={"max_prior_shift_sigma": 3, "allow_synthetic": True})
    rec = _run(st, ds)
    d = rec["discrepancy"]
    assert d["mean_at_data_rms"] > 2e-4  # δ apanha a lomba
    for k, truth in (("CD0", 0.025), ("K", 0.045)):
        p = rec["parameters"][k]
        assert abs(p["value"] - truth) < 3 * p["sd"]
        assert p["sd"] < p["prior"]["sd"]  # os dados informam
    assert rec["method"]["name"] == "koh" and "Kennedy" in rec["method"]["reference"]


# --------------------------------------------------------------------------------- validade e exportações
def _flex_record(tmp_path: Path) -> tuple[dict, Path]:
    out = tmp_path / "flex"
    rec = R.run_study(EX / "flexao_estatica_sintetica.yaml", out)
    return rec, out / "calibration_record.json"


def test_applicable_at_validity_range(tmp_path: Path) -> None:
    rec, _ = _flex_record(tmp_path)
    assert abs(rec["parameters"]["k_EI"]["value"] - 0.92) < 3 * rec["parameters"]["k_EI"]["sd"]
    assert R.applicable_at(rec, "k_EI", {"load": "1.5 kN"})[0]
    ok, why = R.applicable_at(rec, "k_EI", {"load": "3 kN"})
    assert not ok and "fora da gama" in why[0]
    ok, why = R.applicable_at(rec, "k_EI", {})
    assert not ok and "não dada" in why[0]
    assert (tmp_path / "flex" / "provenance.json").is_file()


def test_factors_file_feeds_existing_calibration_loader(tmp_path: Path) -> None:
    from acdt.domains.aircraft.hifi.calibration import _group_of, factor_acceptable, load

    rec, rp = _flex_record(tmp_path)
    ff = R.factors_file(rec, {"load": "1000 N"}, group_of=_group_of, source_path=str(rp))
    f = tmp_path / "cal.json"
    f.write_text(json.dumps(ff), encoding="utf-8")
    applied = load({"calibration": {"file": str(f), "apply": ["structures"]}})
    assert applied == {"k_EI": pytest.approx(rec["parameters"]["k_EI"]["value"])}
    assert load({"calibration": {"file": str(f), "apply": []}}) == {}  # opt-in, como os fatores H1
    out = R.factors_file(rec, {"load": "5000 N"}, group_of=_group_of)
    f.write_text(json.dumps(out), encoding="utf-8")
    assert load({"calibration": {"file": str(f), "apply": ["structures"]}}) == {}  # fora da gama: nunca
    assert not factor_acceptable("k_EI", {"value": 1.0, "decision": "nao_aplicar"})[0]


def test_uq_uses_calibrated_distribution(tmp_path: Path) -> None:
    from acdt.domains.aircraft.hifi.calibration import _group_of
    from acdt.domains.aircraft.uq_run import calibration_inputs

    rec, rp = _flex_record(tmp_path)
    f = tmp_path / "cal.json"
    f.write_text(json.dumps(R.factors_file(rec, {"load": "1000 N"}, group_of=_group_of)), encoding="utf-8")
    raw = {"assumptions": {"calibration": {"file": str(f), "apply": ["structures"]}}}
    ins, exc = calibration_inputs(raw, {"file": str(f)}, tmp_path)
    assert len(ins) == 1 and not exc
    u = ins[0]
    assert u.dist == "normal" and u.params["std"] == pytest.approx(rec["parameters"]["k_EI"]["sd"])
    assert u.path == "assumptions.calibration.factors.k_EI" and "SINTÉTICOS" in u.source
    # target de assumptions: entrada normal + correlação de postos ρ_S = (6/π) asin(ρ/2)
    prec = R.run_study(EX / "polar_tunel_sintetico.yaml")
    frag = R.uq_inputs(prec)
    assert [i["path"] for i in frag["inputs"]] == ["assumptions.aero.oswald"]
    from acdt.core.sensitivity.distributions import parse_input
    assert parse_input(frag["inputs"][0]).dist == "normal"
    assert R.spearman_from_pearson(0.5) == pytest.approx(6 / math.pi * math.asin(0.25))
    assert R.spearman_from_pearson(1.0) == pytest.approx(1.0)


def test_overlay_and_design_db(tmp_path: Path) -> None:
    prec = R.run_study(EX / "polar_tunel_sintetico.yaml")
    ov, refused = R.overlay(prec, {"CL": 0.6})
    assert ov == {"assumptions": {"aero": {"oswald": pytest.approx(prec["parameters"]["e"]["value"])}}}
    ov, refused = R.overlay(prec, {"CL": 1.5})
    assert not ov and refused[0]["target"] == "assumptions.aero.oswald"
    db = DDB.new("t", "aircraft")
    R.to_design_db(db, prec)
    rec2, _ = _flex_record(tmp_path)
    R.to_design_db(db, rec2)  # dois registos no mesmo nível: juntam-se, não se substituem
    blk = db["results"]["calibracao"]["L1"]
    assert blk["fidelity"] == "ensaio"
    qs = blk["quantities"]
    assert qs["polar_tunel_sintetico.e"]["uncertainty"]["kind"] == "desvio_padrao"
    assert qs["flexao_estatica_sintetica.k_EI"]["value"] == pytest.approx(rec2["parameters"]["k_EI"]["value"])
    assert qs["flexao_estatica_sintetica.decisao.k_EI"]["value"] == "aplicar"
    assert DDB.validate(db) == []
    flat = DDB.flatten(db)
    assert flat["results.calibracao.L1.polar_tunel_sintetico.e"]["fidelity"] == "ensaio"
    p = tmp_path / "design.json"
    DDB.save(db, p)
    assert DDB.load(p)["results"]["calibracao"]["L1"]["fidelity"] == "ensaio"
    with pytest.raises(DDB.DesignDBError):
        DDB.set_results(db, "x", "L1", {}, fidelity="palpite")


# ------------------------------------------------------------------------------------- C172S (publicado)
def test_c172s_published_stall_point_is_not_enough() -> None:
    """Um ponto publicado (V_S0 48 KCAS a 1157 kg, S 16,2 m²; resolução de 1 kt, GUM F.2.2.1) contra o CLmax
    de aterragem L0 (Raymer 12.15/12.21) do exemplo: o fator ajusta-se, mas ν = 0 → incerteza desconhecida →
    nao_aplicar. É o comportamento exigido: um ponto não chega para calibrar."""
    from acdt.domains.aircraft.aero.lift import HighLiftDevice, high_lift_summary

    ex = yaml.safe_load((ROOT / "examples" / "cessna172_check.yaml").read_text(encoding="utf-8"))
    a = ex["assumptions"]["aero"]
    hl = high_lift_summary(a["clmax_airfoil"], 0.0, HighLiftDevice(a["flap"]["kind"], a["flap"]["flapped_area_ratio"]))
    src = ("Cessna Aircraft Company, Model 172S Skyhawk SP Information Manual (1998): V_S0 48 KCAS, MTOW 2550 lb, "
           "S 174 ft² (examples/cessna172_check.yaml)")
    ds = I.from_arrays("c172s_vs0", {"V_S0": ([48.0], "kt"), "W": ([1157.0], "kg"), "S": ([16.2], "m**2"),
                                     "CLmax_modelo": ([hl.CLmax_landing], "1")},
                       {"source": src, "kind": "publicado",
                        "conditions": {"flaps": "aterragem (30°)", "potencia": "ralenti", "cg": "dianteiro"},
                        "channels": {"V_S0": {"uncertainty": {"resolution": 1.0, "source": "valor publicado ao kt"}}}})
    st = {"name": "c172s_clmax", "level": "L0",
          "model": {"expr": "sqrt(2*W*g/(rho*S*k*CLmax_modelo))", "output": "V_S0",
                    "units": {"V_S0": "m/s", "W": "kg", "S": "m**2"},
                    "constants": {"g": {"value": 9.80665, "source": "gravidade padrão"},
                                  "rho": {"value": 1.225, "source": "ISA ao nível do mar"}}},
          "parameters": {"k": {"initial": 1.0, "bounds": [0.3, 3.0], "nominal": 1.0}},
          "acceptance": {"min_points": 5, "max_rel_sd": 0.05}}
    rec = _run(st, ds)
    k = rec["parameters"]["k"]
    cl_meas = 2 * 1157 * 9.80665 / (1.225 * 16.2 * (48 * 1852 / 3600) ** 2)
    assert k["value"] == pytest.approx(cl_meas / hl.CLmax_landing, rel=1e-6)
    assert not rec["synthetic"] and rec["fit"]["dof"] == 0
    assert k["sd"] is None and k["decision"] == "nao_aplicar"
    assert any("n = 1" in r for r in k["reasons"])


# ---------------------------------------------------------------------------------------------------- CLI
def test_cli_fit_export_db(tmp_path: Path) -> None:
    def acdt(*a: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "acdt.cli", *a], capture_output=True, text=True, cwd=tmp_path)

    r = acdt("calib", "ingest", str(EX / "polar_tunel_sintetico.csv"))
    assert r.returncode == 0 and "SINTÉTICOS" in r.stdout
    out = tmp_path / "o"
    r = acdt("calib", "fit", str(EX / "flexao_estatica_sintetica.yaml"), "-o", str(out))
    assert r.returncode == 0, r.stderr
    rp = out / "calibration_record.json"
    r = acdt("calib", "export", str(rp), "--at", "load=1200 N", "-o", str(out))
    assert r.returncode == 0 and "aplicar" in r.stdout
    uq = yaml.safe_load((out / "calibration_uq.yaml").read_text(encoding="utf-8"))
    assert uq["calibration"]["factors"] == ["k_EI"]
    ff = json.loads((out / "calibration_factors.json").read_text(encoding="utf-8"))
    assert ff["factors"]["k_EI"]["group"] == "structures" and ff["factors"]["k_EI"]["valid"] is True
    r = acdt("calib", "db", str(rp), "--db", str(tmp_path / "design.json"))
    assert r.returncode == 0, r.stderr
    assert DDB.load(tmp_path / "design.json")["results"]["calibracao"]["L1"]["fidelity"] == "ensaio"
    r = acdt("calib", "show", str(rp))
    assert r.returncode == 0 and "k_EI" in r.stdout
    r = acdt("calib", "fit", str(tmp_path / "nao_existe.yaml"))
    assert r.returncode == 2
