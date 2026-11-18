from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


@pytest.fixture
def ex():
    return EX


@pytest.fixture(scope="session")
def c172_result(tmp_path_factory):
    """Converged Cessna-172-class design (full pipeline), shared by the flight-simulation tests."""
    from acdt.core.pipeline import run_pipeline
    out = tmp_path_factory.mktemp("c172_session")
    return run_pipeline("aircraft", EX / "cessna172_check.yaml", output=out)["result"]


# --------------------------------------------------------------------------- external executables
# Tests that need an external program declare it with a marker (``@pytest.mark.requires_avl`` …). When the program is
# missing the test is *skipped* with a reason starting with ``requires_<tool>`` (never a silent pass), and the session
# summary counts those skips per tool (also written to $GITHUB_STEP_SUMMARY in CI). With
# ``ACDT_REQUIRE_TOOLS=avl,xfoil`` a missing tool becomes a *failure* instead (CI uses it on the jobs that install them,
# so a broken install cannot turn into green-by-skip).
import importlib.util
import os
import shutil
import subprocess
import sys


def _jsbsim_available() -> bool:
    py = os.environ.get("ACDT_JSBSIM_PYTHON", sys.executable)
    if py == sys.executable:
        return importlib.util.find_spec("jsbsim") is not None
    try:
        return subprocess.run([py, "-c", "import jsbsim"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


TOOLS = {
    "avl": lambda: shutil.which("avl") is not None,
    "xfoil": lambda: shutil.which("xfoil") is not None,
    "jsbsim": _jsbsim_available,
}
_TOOL_CACHE: dict = {}


def tool_available(name: str) -> bool:
    if name not in _TOOL_CACHE:
        _TOOL_CACHE[name] = bool(TOOLS[name]())
    return _TOOL_CACHE[name]


def _required_tools() -> set:
    return {t.strip().lower() for t in os.environ.get("ACDT_REQUIRE_TOOLS", "").split(",") if t.strip()}


def pytest_configure(config):
    for t in TOOLS:
        config.addinivalue_line("markers", f"requires_{t}: test needs the external program/package '{t}'")
    # Testes com >= 20 s na CI Linux (2 vCPU). O job Windows corre `-m "not slow"` (docs/QUALIDADE.md §1).
    config.addinivalue_line("markers", "slow: teste lento (>= 20 s na CI Linux); fora do job Windows")


def pytest_runtest_setup(item):
    for t in TOOLS:
        if item.get_closest_marker(f"requires_{t}") is None or tool_available(t):
            continue
        if t in _required_tools():
            pytest.fail(f"requires_{t}: '{t}' em falta mas ACDT_REQUIRE_TOOLS exige-o", pytrace=False)
        pytest.skip(f"requires_{t}: '{t}' não disponível")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    skipped = terminalreporter.stats.get("skipped", [])
    if not skipped:
        return
    counts: dict = {}
    for rep in skipped:
        reason = rep.longrepr[2] if isinstance(rep.longrepr, tuple) else str(rep.longrepr)
        reason = reason.removeprefix("Skipped: ")
        key = reason.split(":")[0] if reason.startswith("requires_") else "outros: " + reason[:90]
        counts[key] = counts.get(key, 0) + 1
    lines = [f"{n:4d}  {k}" for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    terminalreporter.write_sep("-", f"testes saltados por motivo ({len(skipped)})")
    for ln in lines:
        terminalreporter.write_line(ln)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"### Testes saltados: {len(skipped)}\n\n| n | motivo |\n|---:|---|\n")
            for k, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                fh.write(f"| {n} | {k.replace('|', '/')} |\n")
            fh.write("\n")
