"""External high-fidelity tools: discovery and the compute guard.

Executables are looked up in ``$ACDT_HIFI_BIN`` (colon-separated directories, e.g. a conda-forge env with
``su2 calculix gmsh``) and then on ``PATH``. The OpenVSP Python interpreter is ``$ACDT_VSP_PYTHON`` (OpenVSP ships
a CPython-specific ``_vsp.so``). Nothing here installs anything.

Compute guard: every heavy case estimates its memory and run time *before* running (:func:`budget`); if the
estimate exceeds the box (70 % of available RAM, or the time limit), the case is written but not run and the
exact command is returned so it can be run on a stronger machine. Paths stored in the case JSON are
relative to that case folder (:func:`case_relative`); a tool binary is only its file name."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

# A Windows drive path, including one read on an OS where Path.is_absolute() is false.
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


def _repo_root(start: Path) -> Path | None:
    for p in (start, *start.parents):
        if (p / ".git").exists():
            return p
    return None


def case_relative(path: str | Path, case: str | Path) -> str:
    """Posix path relative to the case folder.

    A path that is already relative is not resolved against the process cwd. A path
    inside the git repository that contains ``case`` stays relative, so a sibling
    output folder is ``../other/...``. A tool install outside that repository is the
    file name only, so ``C:\\acdt-tools\\...\\ccx.EXE`` is stored as ``ccx.EXE``.
    """
    text = os.fspath(path)
    if not text or text == "—":
        return text
    if _DRIVE.match(text) and os.name != "nt":
        return PureWindowsPath(text).name
    p = Path(text)
    if not p.is_absolute():
        return p.as_posix()
    case_r = Path(case).resolve()
    target = p.resolve()
    repo = _repo_root(case_r)
    inside_repo = repo is not None and (target == repo or repo in target.parents)
    inside_case = target == case_r or case_r in target.parents
    if inside_repo or inside_case:
        return Path(os.path.relpath(target, case_r)).as_posix()
    return p.name


def resolve_case_path(path: str | Path, case: str | Path) -> Path:
    """Absolute path. A relative ``path`` is taken from the case folder, not from the process cwd."""
    text = os.fspath(path)
    p = Path(text)
    if _DRIVE.match(text) or p.is_absolute():
        return p.resolve()
    return (Path(case) / p).resolve()


def find_exe(name: str) -> str | None:
    # shutil.which with an explicit path honours PATHEXT on Windows (SU2_CFD.exe, ccx.exe, gmsh.exe)
    extra = os.environ.get("ACDT_HIFI_BIN", "")
    if extra:
        hit = shutil.which(name, path=extra)
        if hit:
            return hit
    return shutil.which(name)


def vsp_python() -> str | None:
    p = os.environ.get("ACDT_VSP_PYTHON")
    if p and Path(p).exists():
        return p
    return None


def cores() -> int:
    return os.cpu_count() or 1


def mem_available_gb() -> float:
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullAvailPhys / 1024**3
        except (AttributeError, OSError):
            pass
    return 4.0


@dataclass
class Budget:
    run_here: bool
    mem_gb: float
    time_min: float
    reason: str


def budget(mem_gb: float, time_min: float, max_time_min: float = 45.0) -> Budget:
    avail = mem_available_gb()
    if mem_gb > 0.7 * avail:
        return Budget(False, mem_gb, time_min, f"memória estimada {mem_gb:.1f} GB > 70 % de {avail:.1f} GB disponíveis")
    if time_min > max_time_min:
        return Budget(False, mem_gb, time_min, f"tempo estimado {time_min:.0f} min > limite {max_time_min:.0f} min")
    return Budget(True, mem_gb, time_min, "cabe nesta máquina")


def run(cmd: list[str], cwd: Path, log: str, timeout: float | None = None, env: dict | None = None) -> int:
    """Run an external tool with its log in ``cwd/log``. The executable is recorded for provenance and the case
    folder gets ``provenance.json`` (binary SHA-256, platform, commit; :mod:`acdt.core.provenance`)."""
    from acdt.core import provenance

    _record_tools(cmd)
    e = dict(os.environ, **(env or {}))
    with open(Path(cwd) / log, "w") as f:
        p = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, env=e)
    provenance.note_output(cwd, entry_point=f"hifi.tools.run({Path(str(cmd[0])).stem})")
    return p.returncode


def _record_tools(cmd: list[str]) -> None:
    """Provenance names: the launcher (``mpirun``), the solver behind it, or ``python (<script>)``."""
    from acdt.core import provenance

    if not cmd:
        return
    first = Path(str(cmd[0]))
    stem = first.stem.lower()
    if stem in ("mpirun", "mpiexec"):
        provenance.tool_used(first.stem, cmd[0])
        rest = [c for c in cmd[1:] if not str(c).startswith("-") and not str(c).isdigit()]
        if rest:
            provenance.tool_used(Path(str(rest[0])).stem, rest[0])
    elif stem.startswith("python") and len(cmd) > 1 and str(cmd[1]).endswith(".py"):
        provenance.tool_used(f"python ({Path(str(cmd[1])).name})", cmd[0])
    else:
        provenance.tool_used(first.stem, cmd[0])


def mpi_prefix(n: int) -> list[str]:
    mpirun = find_exe("mpirun") or find_exe("mpiexec")
    return [mpirun, "-n", str(n)] if (mpirun and n > 1) else []


def run_gmsh(geo: str, work: str | Path, geo_name: str, out: str | Path, dim: int,
             timeout: float | None = 780) -> Path:
    """Mesh a Gmsh ``.geo`` script with the **gmsh executable as a separate process** and write SU2 format.

    acdt never imports the Gmsh library (GPL-2.0-or-later) in-process: the ``.geo`` text is written to
    ``work/geo_name`` and ``gmsh <geo> -<dim> -format su2 -o <out>`` is run (``$ACDT_HIFI_BIN`` / ``PATH``), so
    acdt and Gmsh stay separate programs communicating through files (THIRD_PARTY.md)."""
    exe = find_exe("gmsh")
    if exe is None:
        from ..aero.interfaces import ToolNotAvailable
        raise ToolNotAvailable("gmsh executable not found (set ACDT_HIFI_BIN or put gmsh on PATH)")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / geo_name).write_text(geo)
    out = Path(out)
    log = Path(geo_name).stem + "_gmsh.log"
    rc = run([exe, geo_name, f"-{dim}", "-format", "su2", "-o", str(out.resolve()), "-nopopup"], work, log,
             timeout=timeout)
    if rc != 0 or not out.exists():
        tail = (work / log).read_text(errors="replace")[-2000:] if (work / log).exists() else ""
        raise RuntimeError(f"gmsh failed (rc {rc}) on {work / geo_name}:\n{tail}")
    return out


def su2_nelem(path: str | Path) -> int:
    """Number of interior (volume in 3-D, surface in 2-D) elements of an SU2 mesh (first ``NELEM=``)."""
    with open(path) as f:
        for line in f:
            if line.startswith("NELEM="):
                return int(line.split("=")[1])
    raise ValueError(f"no NELEM in {path}")
