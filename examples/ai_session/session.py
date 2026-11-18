"""Scripted MCP client session — what an AI agent does with acdt, end to end.

The 'user' asks (PT): "Quero um UAV elétrico de vigilância, 4 kg de carga útil, pelo menos 2,5 h de autonomia,
até 25 kg, envergadura até 4,5 m." The agent:

1. reads the requirement schema and validates the request (lenient units);
2. takes the closest repository example (``uav_endurance_payload``) as the template for the assumptions —
   recorded as such in the run — and replaces its requirements with the user's;
3. sizes at L0 (handbook), then L1 (XFOIL/AVL);
4. runs the MDO (trust region; reduced settings for the demo: L0 truth pipeline, 1 iteration, value-only
   correction);
5. writes the design dossier, and asks for the compute plan of the hifi verification (heavy steps → needs the
   user's approval; nothing heavy is run).

The session uses the official MCP client over the in-memory transport (same tools/JSON as stdio/HTTP).
Usage: ``python examples/ai_session/session.py [--out DIR] [--full]`` (``--full``: L1 MDO, 2 iterations).
Writes ``transcript.json``, ``transcript.md`` (every call, its arguments and the structured result) and a copy of
the dossier; the runs go to ``$ACDT_RUNS_DIR`` (default ``<out>/runs``)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import anyio
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

USER_REQUEST = {
    "propulsion_type": "electric",
    "payload_mass": "4 kg",
    "endurance": {"min": "2.5 h"},
    "mtow": {"max": "25 kg"},
    "wing_span": {"max": "4.5 m"},
    "cruise_speed": {"target": "22 m/s"},
    "cruise_altitude": {"target": "600 m"},
    "stall_speed": {"max": "13 m/s"},
    "climb_rate": {"min": "3 m/s"},
    "service_ceiling": {"min": "3000 m"},
    "regulatory_category": "easa_specific",
}


def _sc(r):
    sc = getattr(r, "structured_content", None) or getattr(r, "structuredContent", None)
    if sc is None and r.content:
        try:
            sc = json.loads(r.content[0].text)
        except Exception:
            sc = {"text": r.content[0].text}
    if isinstance(sc, dict) and set(sc) == {"result"}:
        sc = sc["result"]
    return sc


async def session(full: bool = False) -> list[dict]:
    from mcp import Client
    from acdt.ai.mcp_server import build_server
    log: list[dict] = []

    async with Client(build_server()) as c:
        async def call(tool, args, note):
            t0 = time.perf_counter()
            r = await c.call_tool(tool, args)
            sc = _sc(r)
            if isinstance(sc, dict) and sc.get("job_id") and sc.get("status") in ("queued", "running"):
                r = await c.call_tool("job_status", {"job_id": sc["job_id"], "wait_s": 600})
                js = _sc(r)
                sc = js.get("result") or js
            err = bool(getattr(r, "is_error", getattr(r, "isError", False)))
            log.append({"tool": tool, "note": note, "arguments": args, "is_error": err,
                        "seconds": round(time.perf_counter() - t0, 1), "result": sc})
            print(f"[session] {tool:22s} {log[-1]['seconds']:7.1f} s  {note}", file=sys.stderr)
            if err:
                raise RuntimeError(f"{tool}: {sc}")
            return sc

        await call("requirements_schema", {}, "learn requirement keys, units and senses")
        v = await call("validate_requirements", {"spec": {"name": "UAV ISR (pedido do utilizador)",
                                                          "aircraft_class": "uav_small",
                                                          "requirements": USER_REQUEST}},
                       "validate + normalise the user's request")
        assert v["ok"], v
        tmpl = yaml.safe_load((REPO / "examples" / "uav_endurance_payload.yaml").read_text(encoding="utf-8"))
        spec = {**tmpl, "name": "UAV ISR (pedido do utilizador)", "requirements": v["normalised_spec"]["requirements"],
                "description": "template: examples/uav_endurance_payload.yaml (assumptions, systems); requirements "
                               "from the user"}
        spec["assumption_sources"] = {"*": "template examples/uav_endurance_payload.yaml (sources in its comments)"}
        spec.pop("systems", None)        # systems selection is its own step (tool 'systems'); not in this demo
        s0 = await call("size", {"spec": spec, "level": "L0", "wait_s": 600}, "conceptual sizing, handbook (L0)")
        s1 = await call("size", {"run_id": s0["run_id"], "level": "L1", "wait_s": 600},
                        "low-fidelity sizing, XFOIL/AVL in the loop (L1)")
        opt_args = {"run_id": s1["run_id"], "max_iter": 2 if full else 1, "wait_s": 600}
        if not full:
            opt_args.update(level="L0", consistency_order=0)
        o = await call("optimize", opt_args, "MDO, trust region" + ("" if full else " (demo settings)"))
        await call("compare_runs", {"run_ids": [s0["run_id"], s1["run_id"]]}, "L0 vs L1 (the MDO result carries "
                                                                              "its own baseline vs optimum)")
        await call("hifi_estimate", {"steps": ["fem", "flutter", "cfd2d"]},
                   "compute plan for verification — cfd2d is heavy and needs the user's approval")
        await call("generate_report", {"run_ids": [s0["run_id"], s1["run_id"], o["run_id"]],
                                       "title": "UAV ISR — sessão de demonstração",
                                       "notes": "Demo scripted session (examples/ai_session/session.py)."},
                   "design dossier")
    return log


def write(log: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "transcript.json").write_text(json.dumps(log, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    L = ["# acdt — sessão MCP de demonstração (transcrição)", "",
         "Gerado por `examples/ai_session/session.py`; números tal como devolvidos pelas ferramentas.", "",
         "| # | ferramenta | s | nota |", "|---|---|---|---|"]
    L += [f"| {i} | `{e['tool']}` | {e['seconds']} | {e['note']} |" for i, e in enumerate(log, 1)]
    for i, e in enumerate(log, 1):
        res = e["result"]
        if e["tool"] == "requirements_schema":
            res = {"(omitted)": "schema", "n_types": len((res or {}).get("requirement_types", []) or [])}
        L += ["", f"## {i}. `{e['tool']}` — {e['note']}", "", "argumentos:", "```json",
              json.dumps(e["arguments"], ensure_ascii=False, default=str)[:1500], "```", "resultado (excerto):",
              "```json", json.dumps(res, indent=1, ensure_ascii=False, default=str)[:4000], "```"]
    (out / "transcript.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "output"))
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args(argv)
    os.environ.setdefault("ACDT_RUNS_DIR", str(Path(a.out) / "runs"))
    log = anyio.run(session, a.full)
    write(log, Path(a.out))
    rep = log[-1]["result"]["files"]
    import shutil
    shutil.copyfile(rep["dossier_md"], Path(a.out) / "dossier.md")
    print(f"[session] transcript: {Path(a.out) / 'transcript.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
