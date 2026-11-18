"""Run registry and provenance (``runs/<run_id>/run.json``).

Every toolkit call that computes something creates a *run*: a folder with the materialised inputs (the mission
YAML actually analysed), the outputs, and ``run.json`` with

* ``inputs`` — the arguments of the call (spec, options);
* ``assumptions`` — every value the analysis used that did not come from the user, each with ``source`` =
  citation / ``"assumed (acdt default)"`` / ``"user"`` / external-data provenance;
* ``versions`` — acdt version, Python, key libraries, external executables found; ``git`` — commit + dirty flag;
* ``outputs`` (structured summary) and ``files`` (paths of reports/plots/JSON);
* ``calibration`` — the calibration block applied (file, groups, factors) and ``external_data`` provenance.

The root is ``$ACDT_RUNS_DIR`` or ``./runs`` (relative to the current directory of the server)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()
REPO_ROOT = Path(__file__).resolve().parents[3]


def runs_root() -> Path:
    p = Path(os.environ.get("ACDT_RUNS_DIR") or (Path.cwd() / "runs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def git_info() -> dict:
    def g(*a):
        r = subprocess.run(["git", *a], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    try:
        h = g("rev-parse", "HEAD")
        if not h:
            return {"commit": None, "note": "not a git checkout (installed package?)"}
        return {"commit": h, "dirty": bool(g("status", "--porcelain", "--untracked-files=no")),
                "branch": g("rev-parse", "--abbrev-ref", "HEAD")}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "note": "git not available"}


_VERSIONS_CACHE: dict | None = None


def versions() -> dict:
    """acdt / Python / library versions and which external executables are visible (path only, not run)."""
    global _VERSIONS_CACHE
    if _VERSIONS_CACHE is not None:
        return _VERSIONS_CACHE
    from importlib import metadata

    import acdt

    libs = {}
    for name in ("numpy", "scipy", "matplotlib", "openmdao", "openaerostruct", "neuralfoil", "mcp", "pyyaml"):
        try:
            libs[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            libs[name] = None
    exes = {}
    try:
        from acdt.domains.aircraft.hifi.tools import find_exe, vsp_python
        for e in ("avl", "xfoil", "gmsh", "SU2_CFD", "ccx", "mpirun"):
            exes[e] = find_exe(e)
        exes["openvsp_python"] = vsp_python()
    except Exception as ex:  # pragma: no cover - defensive
        exes["error"] = str(ex)
    import shutil
    for e in ("avl", "xfoil"):
        exes[e] = exes.get(e) or shutil.which(e)
    _VERSIONS_CACHE = {"acdt": acdt.__version__, "python": sys.version.split()[0], "platform": platform.platform(),
                       "libraries": libs, "executables": exes}
    return _VERSIONS_CACHE


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_").lower()[:40] or "run"


class Run:
    """One registered run. ``record`` is the dict persisted as ``run.json``."""

    def __init__(self, path: Path, record: dict):
        self.path, self.record = Path(path), record

    @property
    def id(self) -> str:
        return self.record["run_id"]

    def save(self) -> "Run":
        with _LOCK:
            tmp = self.path / "run.json.tmp"
            tmp.write_text(json.dumps(self.record, indent=1, default=_json_default, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(self.path / "run.json")
        return self

    def finish(self, outputs: dict | None = None, files: dict | None = None, status: str = "done",
               error: str | None = None) -> "Run":
        r = self.record
        r["status"], r["finished"] = status, now_iso()
        if outputs is not None:
            r["outputs"] = outputs
        if files:
            r.setdefault("files", {}).update({k: str(v) for k, v in files.items() if v})
        if error:
            r["error"] = error
        r["provenance"] = _provenance(r, self.path)
        return self.save()


def _json_default(o):
    if isinstance(o, Path):
        return str(o)
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:  # pragma: no cover
        pass
    if hasattr(o, "__dict__"):
        return {k: v for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def new_run(tool: str, name: str, inputs: dict, parent: str | None = None) -> Run:
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    rid = f"{ts}-{_slug(tool)}-{_slug(name)}-{secrets.token_hex(2)}"
    p = runs_root() / rid
    p.mkdir(parents=True)
    rec = {"run_id": rid, "tool": tool, "name": name, "status": "running", "created": now_iso(), "finished": None,
           "parent_run": parent, "inputs": inputs, "assumptions": [], "external_data": [], "calibration": None,
           "versions": versions(), "git": git_info(), "outputs": None, "files": {}, "dir": str(p)}
    rec["provenance"] = _provenance(rec, p)
    return Run(p, rec).save()


def _provenance(rec: dict, path: Path) -> dict:
    """Registo ``acdt.provenance/1`` (:mod:`acdt.core.provenance`) da corrida MCP, com manifesto da pasta.
    As ferramentas são as usadas neste processo até agora (o servidor MCP pode correr várias corridas em
    paralelo: a lista é um majorante, nunca omite uma ferramenta usada)."""
    from acdt.core import provenance as P

    sc = P.RunScope(entry_point=f"mcp {rec.get('tool')}", argv=[], tools=P.tools_used_globally())
    spec = (rec.get("files") or {}).get("spec") or (rec.get("inputs") or {}).get("spec")
    if isinstance(spec, str) and len(spec) < 4096 and Path(spec).is_file():
        sc.inputs[str(Path(spec).resolve())] = P.hash_input(spec)
    seed = (rec.get("inputs") or {}).get("seed")
    if seed is not None:
        sc.seeds["seed"] = seed
    out = P.collect(scope=sc)
    out["inputs_call_sha256"] = P.canonical_hash(json.loads(json.dumps(rec.get("inputs"), default=_json_default)))
    return out


def load(run_id: str) -> Run:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", run_id or ""):
        raise KeyError(f"invalid run id {run_id!r}")
    p = runs_root() / run_id
    f = p / "run.json"
    if not f.exists():
        raise KeyError(f"run {run_id!r} not found in {runs_root()}")
    return Run(p, json.loads(f.read_text(encoding="utf-8")))


def list_runs(tool: str | None = None, limit: int = 50) -> list[dict]:
    out = []
    for f in sorted(runs_root().glob("*/run.json"), reverse=True):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if tool and r.get("tool") != tool:
            continue
        out.append({k: r.get(k) for k in ("run_id", "tool", "name", "status", "created", "parent_run")})
        if len(out) >= limit:
            break
    return out
