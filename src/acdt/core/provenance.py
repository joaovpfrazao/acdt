"""Proveniência dos resultados: de onde veio cada número (registo ``acdt.provenance/1``).

Cada corrida que escreve resultados deixa, ao lado deles, um registo JSON com:

* ``acdt`` — versão do pacote, *commit* git, ramo e se a árvore estava suja (``dirty``);
* ``python`` / ``packages`` — versão do interpretador e das bibliotecas que mexem nos números;
* ``platform`` — SO, versão e arquitectura (o AVL oficial de Windows e o compilado em Linux diferem no 3.º/4.º
  algarismo, ver ``docs/QUALIDADE.md`` §4);
* ``tools`` — identidade de cada executável externo **usado** nesta corrida (AVL, XFOIL, SU2, CalculiX, Gmsh,
  intérprete do JSBSim/CadQuery/OpenVSP…): caminho, SHA-256 do binário, tamanho, data e, quando há uma opção de
  versão não-interactiva conhecida, a linha de versão;
* ``inputs`` — SHA-256 de cada ficheiro de entrada. YAML/JSON são hashed na forma **canónica** (``json.dumps``
  com chaves ordenadas do conteúdo carregado), por isso comentários, ordem das chaves e espaços não mudam o hash;
* ``seeds`` — sementes aleatórias declaradas;
* ``created`` — instante em UTC e em Europe/Lisbon; ``entry_point`` — comando, argumentos e pasta de trabalho;
* ``outputs`` — manifesto dos ficheiros na pasta de saída (SHA-256, tamanho, se foram escritos nesta corrida).

Onde é escrito (pontos centrais, não módulo a módulo): ``acdt.cli.main`` abre um :func:`run_scope` à volta de
cada subcomando; :func:`acdt.core.pipeline.run_pipeline` com ``output=`` e o orquestrador ``hifi`` chamam
:func:`note_output`; o registo de corridas MCP (``acdt.ai.registry``) junta o registo ao ``run.json``. Uma pasta
de saída recebe ``provenance.json``; um ficheiro de saída ``x.json`` recebe ``x.provenance.json`` ao lado. Os
resultados em si não mudam. ``ACDT_PROVENANCE=0`` desliga a escrita (o registo continua disponível em memória).

Comparação: :func:`compare` (e ``acdt provenance diff A B``) explica porque dois resultados podem diferir.

Sem rede. Só lê ficheiros locais e corre ``git`` (e, para ferramentas com opção de versão conhecida, o próprio
executável com tempo-limite de 5 s).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

SCHEMA = "acdt.provenance/1"
SIDECAR_DIR_NAME = "provenance.json"
SIDECAR_SUFFIX = ".provenance.json"

#: Bibliotecas cujas versões podem mudar números (as ausentes ficam ``None``, não são omitidas).
KEY_PACKAGES: tuple[str, ...] = ("numpy", "scipy", "matplotlib", "pyyaml", "openmdao", "openaerostruct",
                                 "aerosandbox", "neuralfoil", "pyNastran", "PanelAero", "jsbsim", "mcp")

#: Opções de versão não-interactivas conhecidas. AVL e XFOIL são interactivos (sem ``--version``): a identidade
#: deles é o SHA-256 do binário.
VERSION_PROBES: dict[str, tuple[str, ...]] = {"gmsh": ("--version",), "ccx": ("-v",)}

#: Ficheiros maiores do que isto entram no manifesto só com tamanho (malhas, soluções CFD).
MAX_HASH_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_FILES = 5000

_LOCK = threading.Lock()
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GIT_CACHE: dict[str, Any] | None = None
_SHA_CACHE: dict[tuple[str, int, int], str] = {}
_PROBE_CACHE: dict[tuple[str, int, int], str | None] = {}
_GLOBAL_TOOLS: dict[str, str] = {}


# --------------------------------------------------------------------------------------------------- utilidades
def sha256_file(path: str | os.PathLike[str]) -> str:
    """SHA-256 do conteúdo do ficheiro (lido aos blocos), com cache por (caminho, tamanho, mtime)."""
    p = Path(path)
    st = p.stat()
    key = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    with _LOCK:
        hit = _SHA_CACHE.get(key)
    if hit is not None:
        return hit
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    d = h.hexdigest()
    with _LOCK:
        _SHA_CACHE[key] = d
    return d


def _json_default(o: Any) -> Any:
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=repr)
    item = getattr(o, "item", None)          # escalares numpy
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    tolist = getattr(o, "tolist", None)      # ndarray
    if callable(tolist):
        return tolist()
    raise TypeError(f"não serializável de forma canónica: {type(o).__name__}")


def canonical_json(obj: Any) -> str:
    """Forma canónica: chaves ordenadas, separadores fixos, UTF-8 sem escapes. Igual em qualquer SO."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def canonical_hash(obj: Any) -> str:
    """SHA-256 da forma canónica de um objecto JSON-serializável (dict/list/números/strings)."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def hash_input(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Identidade de um ficheiro de entrada. YAML/JSON: hash canónico do conteúdo carregado (``kind`` =
    ``yaml-canonical``/``json-canonical``) mais o hash dos bytes; outros: só os bytes."""
    p = Path(path)
    rec: dict[str, Any] = {"path": str(p.resolve()), "sha256_bytes": sha256_file(p), "size_bytes": p.stat().st_size}
    suf = p.suffix.lower()
    try:
        if suf in (".yaml", ".yml"):
            import yaml

            rec["kind"] = "yaml-canonical"
            rec["sha256"] = canonical_hash(yaml.safe_load(p.read_text(encoding="utf-8")))
        elif suf == ".json":
            rec["kind"] = "json-canonical"
            rec["sha256"] = canonical_hash(json.loads(p.read_text(encoding="utf-8")))
        else:
            rec["kind"], rec["sha256"] = "bytes", rec["sha256_bytes"]
    except (ValueError, TypeError, UnicodeDecodeError, ImportError) as ex:
        rec["kind"], rec["sha256"] = "bytes", rec["sha256_bytes"]
        rec["note"] = f"forma canónica indisponível ({type(ex).__name__}); usado o hash dos bytes"
    except Exception as ex:  # yaml.YAMLError e afins: o ficheiro não é YAML válido
        rec["kind"], rec["sha256"] = "bytes", rec["sha256_bytes"]
        rec["note"] = f"forma canónica indisponível ({type(ex).__name__}); usado o hash dos bytes"
    return rec


def timestamps(now: _dt.datetime | None = None) -> dict[str, str | None]:
    """Instante em UTC e em Europe/Lisbon (``None`` se a base de fusos não existir, p.ex. Windows sem tzdata)."""
    t = (now or _dt.datetime.now(_dt.timezone.utc)).astimezone(_dt.timezone.utc)
    out: dict[str, str | None] = {"utc": t.isoformat(timespec="seconds"), "europe_lisbon": None}
    try:
        from zoneinfo import ZoneInfo

        out["europe_lisbon"] = t.astimezone(ZoneInfo("Europe/Lisbon")).isoformat(timespec="seconds")
    except Exception:  # ZoneInfoNotFoundError (Windows sem o pacote tzdata)
        pass
    return out


def git_info(refresh: bool = False) -> dict[str, Any]:
    """*Commit*, ramo e estado (``dirty`` = alterações em ficheiros seguidos) do checkout do acdt."""
    global _GIT_CACHE
    if _GIT_CACHE is not None and not refresh:
        return dict(_GIT_CACHE)

    def g(*a: str) -> str | None:
        r = subprocess.run(["git", *a], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None

    info: dict[str, Any]
    try:
        h = g("rev-parse", "HEAD")
        if not h:
            info = {"commit": None, "dirty": None, "branch": None, "note": "não é um checkout git (pacote instalado?)"}
        else:
            st = g("status", "--porcelain", "--untracked-files=no")
            info = {"commit": h, "dirty": None if st is None else bool(st),
                    "branch": g("rev-parse", "--abbrev-ref", "HEAD"), "dirty_diff_sha256": None}
            if st:  # identidade das alterações não commitadas (ficheiros seguidos), para comparar duas árvores sujas
                r = subprocess.run(["git", "diff", "HEAD", "--binary"], cwd=_REPO_ROOT, capture_output=True,
                                   timeout=30)
                if r.returncode == 0:
                    info["dirty_diff_sha256"] = hashlib.sha256(r.stdout).hexdigest()
    except (OSError, subprocess.SubprocessError):
        info = {"commit": None, "dirty": None, "branch": None, "note": "git indisponível"}
    _GIT_CACHE = info
    return dict(info)


def package_versions(names: Sequence[str] = KEY_PACKAGES) -> dict[str, str | None]:
    from importlib import metadata

    out: dict[str, str | None] = {}
    for n in names:
        try:
            out[n] = metadata.version(n)
        except metadata.PackageNotFoundError:
            out[n] = None
    return out


def platform_info() -> dict[str, str]:
    return {"system": platform.system(), "release": platform.release(), "version": platform.version(),
            "machine": platform.machine(), "platform": platform.platform()}


def python_info() -> dict[str, str]:
    return {"version": platform.python_version(), "implementation": platform.python_implementation(),
            "executable": sys.executable}


def _probe_version(name: str, path: Path) -> str | None:
    args = VERSION_PROBES.get(name) or VERSION_PROBES.get(Path(name).stem)
    if not args:
        return None
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    with _LOCK:
        if key in _PROBE_CACHE:
            return _PROBE_CACHE[key]
    v: str | None
    try:
        r = subprocess.run([str(path), *args], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
        lines = [ln.strip() for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
        v = lines[0][:200] if lines else None
    except (OSError, subprocess.SubprocessError):
        v = None
    with _LOCK:
        _PROBE_CACHE[key] = v
    return v


def tool_identity(name: str, path: str | os.PathLike[str] | None, probe: bool = True) -> dict[str, Any]:
    """Identidade de um executável: caminho resolvido, SHA-256, tamanho, mtime (UTC) e versão (se houver sonda)."""
    if not path:
        return {"name": name, "path": None, "found": False}
    p = Path(path)
    try:
        p = p.resolve()
        st = p.stat()
    except OSError as ex:
        return {"name": name, "path": str(path), "found": False, "error": f"{type(ex).__name__}: {ex}"}
    rec: dict[str, Any] = {"name": name, "path": str(p), "found": True, "size_bytes": st.st_size,
                           "mtime_utc": _dt.datetime.fromtimestamp(st.st_mtime, _dt.timezone.utc)
                           .isoformat(timespec="seconds"), "sha256": None, "version": None}
    try:
        rec["sha256"] = sha256_file(p)
    except OSError as ex:
        rec["error"] = f"{type(ex).__name__}: {ex}"
    if probe:
        rec["version"] = _probe_version(name, p)
    if rec["version"] is None:
        rec["version_note"] = "sem opção de versão não-interactiva conhecida: a identidade é o SHA-256 do binário"
    return rec


# ------------------------------------------------------------------------------------------ âmbito de corrida
@dataclass
class RunScope:
    """Estado de uma corrida (um subcomando da CLI, uma corrida MCP)."""

    entry_point: str
    argv: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    tools: dict[str, str] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    seeds: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, None] = field(default_factory=dict)   # caminhos (ordem de chegada)
    notes: list[str] = field(default_factory=list)


_SCOPES: list[RunScope] = []


def current_scope() -> RunScope | None:
    with _LOCK:
        return _SCOPES[-1] if _SCOPES else None


def enabled() -> bool:
    return os.environ.get("ACDT_PROVENANCE", "1").strip().lower() not in ("0", "false", "no", "off")


def tool_used(name: str, path: str | os.PathLike[str] | None) -> None:
    """Regista que o executável ``name`` (em ``path``) vai ser corrido. Chamado junto de cada ``subprocess``
    que lança uma ferramenta externa. Barato: o hash só é calculado quando o registo é montado."""
    if not path:
        return
    with _LOCK:
        _GLOBAL_TOOLS[name] = str(path)
        if _SCOPES:
            _SCOPES[-1].tools[name] = str(path)


def tools_used_globally() -> dict[str, str]:
    with _LOCK:
        return dict(_GLOBAL_TOOLS)


def note_input(path: str | os.PathLike[str]) -> None:
    sc = current_scope()
    if sc is None:
        return
    p = Path(path)
    if p.is_file():
        k = str(p.resolve())
        if k not in sc.inputs:
            sc.inputs[k] = hash_input(p)


def register_seed(name: str, value: Any) -> None:
    sc = current_scope()
    if sc is not None:
        sc.seeds[name] = value


@contextlib.contextmanager
def run_scope(entry_point: str, argv: Sequence[str] | None = None, inputs: Sequence[str | os.PathLike[str]] = (),
              seeds: Mapping[str, Any] | None = None) -> Iterator[RunScope]:
    """Abre uma corrida. À saída (também em erro) escreve o registo em cada saída anotada com :func:`note_output`."""
    sc = RunScope(entry_point=entry_point, argv=list(argv if argv is not None else sys.argv[1:]))
    with _LOCK:
        _SCOPES.append(sc)
    try:
        for p in inputs:
            note_input(p)
        for k, v in (seeds or {}).items():
            register_seed(k, v)
        yield sc
    finally:
        with _LOCK:
            if sc in _SCOPES:
                _SCOPES.remove(sc)
        if enabled():
            for out in list(sc.outputs):
                with contextlib.suppress(OSError):
                    write_sidecar(out, scope=sc)


def note_output(path: str | os.PathLike[str], inputs: Sequence[str | os.PathLike[str]] = (),
                entry_point: str | None = None, since: float | None = None) -> Path | None:
    """Anota uma saída (pasta ou ficheiro). Dentro de :func:`run_scope` o registo é escrito no fim da corrida;
    fora dele (uso da biblioteca) é escrito já, com um âmbito implícito. Devolve o caminho do registo escrito
    agora (ou ``None``)."""
    sc = current_scope()
    if sc is not None:
        for p in inputs:
            note_input(p)
        sc.outputs[str(Path(path))] = None
        return None
    if not enabled():
        return None
    tmp = RunScope(entry_point=entry_point or _guess_entry_point(), argv=list(sys.argv[1:]),
                   started=since if since is not None else time.time())
    tmp.tools = tools_used_globally()
    for p in inputs:
        q = Path(p)
        if q.is_file():
            tmp.inputs[str(q.resolve())] = hash_input(q)
    try:
        return write_sidecar(path, scope=tmp)
    except OSError:
        return None


def _guess_entry_point() -> str:
    return f"python {Path(sys.argv[0]).name}" if sys.argv and sys.argv[0] else "python"


# ----------------------------------------------------------------------------------------------- o registo
def collect(scope: RunScope | None = None, entry_point: str | None = None, argv: Sequence[str] | None = None,
            inputs: Sequence[str | os.PathLike[str]] = (), seeds: Mapping[str, Any] | None = None,
            tools: Mapping[str, str | os.PathLike[str] | None] | None = None,
            probe_versions: bool = True) -> dict[str, Any]:
    """Monta o registo ``acdt.provenance/1`` (sem manifesto de saídas; ver :func:`write_sidecar`)."""
    import acdt

    sc = scope if scope is not None else current_scope()
    tl: dict[str, str | os.PathLike[str] | None] = dict(sc.tools) if sc else {}
    tl.update(tools or {})
    ins: dict[str, dict[str, Any]] = dict(sc.inputs) if sc else {}
    for p in inputs:
        q = Path(p)
        if q.is_file():
            ins.setdefault(str(q.resolve()), hash_input(q))
    sd: dict[str, Any] = dict(sc.seeds) if sc else {}
    sd.update(seeds or {})
    ep = entry_point or (sc.entry_point if sc else _guess_entry_point())
    av = list(argv) if argv is not None else (sc.argv if sc else list(sys.argv[1:]))
    rec: dict[str, Any] = {
        "schema": SCHEMA,
        "created": timestamps(),
        "entry_point": {"command": ep, "argv": av, "cwd": str(Path.cwd())},
        "acdt": {"version": acdt.__version__, "git": git_info()},
        "python": python_info(),
        "packages": package_versions(),
        "platform": platform_info(),
        "tools": {n: tool_identity(n, p, probe=probe_versions) for n, p in sorted(tl.items())},
        "inputs": [ins[k] for k in sorted(ins)],
        "seeds": sd,
        "notes": list(sc.notes) if sc else [],
    }
    if not sd:
        rec["notes"].append("nenhuma semente declarada nesta corrida (desconhecido ≠ determinístico)")
    return rec


def _manifest(root: Path, since: float) -> tuple[list[dict[str, Any]], list[str]]:
    files: list[dict[str, Any]] = []
    notes: list[str] = []
    paths = sorted(q for q in root.rglob("*") if q.is_file() and not _is_sidecar(q))
    if len(paths) > MAX_MANIFEST_FILES:
        notes.append(f"manifesto truncado: {len(paths)} ficheiros, listados {MAX_MANIFEST_FILES}")
        paths = paths[:MAX_MANIFEST_FILES]
    for q in paths:
        try:
            st = q.stat()
        except OSError:
            continue
        e: dict[str, Any] = {"path": q.relative_to(root).as_posix(), "size_bytes": st.st_size,
                             "written_this_run": st.st_mtime >= since - 2.0}
        if st.st_size <= MAX_HASH_BYTES:
            try:
                e["sha256"] = sha256_file(q)
            except OSError:
                e["sha256"] = None
        else:
            e["sha256"] = None
            e["note"] = "maior do que MAX_HASH_BYTES: só o tamanho"
        files.append(e)
    return files, notes


def _is_sidecar(p: Path) -> bool:
    return p.name == SIDECAR_DIR_NAME or p.name.endswith(SIDECAR_SUFFIX)


def sidecar_path(output: str | os.PathLike[str]) -> Path:
    """Onde fica o registo de uma saída: ``<pasta>/provenance.json`` ou ``<ficheiro sem sufixo>.provenance.json``."""
    p = Path(output)
    if p.is_dir():
        return p / SIDECAR_DIR_NAME
    return p.with_name(p.stem + SIDECAR_SUFFIX)


def write_sidecar(output: str | os.PathLike[str], scope: RunScope | None = None) -> Path | None:
    """Escreve o registo junto da saída (pasta ou ficheiro). Devolve o caminho, ou ``None`` se a saída não existe."""
    p = Path(output)
    if not p.exists():
        return None
    sc = scope if scope is not None else current_scope()
    rec = collect(scope=sc)
    since = sc.started if sc else time.time()
    if p.is_dir():
        rec["outputs"], extra = _manifest(p, since)
        rec["notes"] += extra
    else:
        st = p.stat()
        rec["outputs"] = [{"path": p.name, "size_bytes": st.st_size, "written_this_run": st.st_mtime >= since - 2.0,
                           "sha256": sha256_file(p) if st.st_size <= MAX_HASH_BYTES else None}]
    target = sidecar_path(p)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(target)
    return target


def load(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Lê um registo a partir de: um ``provenance.json``/``*.provenance.json``; uma pasta de saída; um ficheiro de
    resultado (procura o registo ao lado); ou um ``run.json`` do registo MCP (chave ``provenance``)."""
    p = Path(path)
    cands: list[Path] = []
    if p.is_dir():
        cands = [p / SIDECAR_DIR_NAME, p / "run.json"]
    elif _is_sidecar(p):
        cands = [p]
    else:
        cands = [sidecar_path(p), p.parent / SIDECAR_DIR_NAME, p]
    for c in cands:
        if not c.is_file():
            continue
        try:
            d = json.loads(c.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("schema") == SCHEMA:
            return d
        if isinstance(d, dict) and isinstance(d.get("provenance"), dict):
            prov: dict[str, Any] = d["provenance"]
            return prov
    raise FileNotFoundError(f"nenhum registo {SCHEMA} encontrado para {p}")


# -------------------------------------------------------------------------------------------- comparação
def _get(d: Mapping[str, Any], *keys: str) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(k)
    return cur


def compare(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Explica porque dois resultados podem diferir. Devolve ``{"identicos", "reprodutivel",
    "avisos_reprodutibilidade", "diferencas"}``; cada diferença tem ``campo``, ``a``, ``b``, ``peso``
    (``alto``/``medio``/``info``) e ``porque`` (pt-PT).

    ``identicos`` = nenhuma diferença de peso ``alto``/``medio`` entre os dois registos (instante e caminhos não
    contam). ``reprodutivel`` = nenhuma das corridas tinha árvore suja ou estado git desconhecido."""
    D: list[dict[str, Any]] = []
    reprod: list[str] = []

    def add(campo: str, va: Any, vb: Any, peso: str, porque: str) -> None:
        D.append({"campo": campo, "a": va, "b": vb, "peso": peso, "porque": porque})

    if a.get("schema") != b.get("schema"):
        add("schema", a.get("schema"), b.get("schema"), "medio", "versões diferentes do formato de proveniência")
    ca, cb = _get(a, "acdt", "git", "commit"), _get(b, "acdt", "git", "commit")
    if ca != cb:
        add("acdt.git.commit", ca, cb, "alto", "código do acdt diferente: métodos ou valores por omissão podem ter "
            "mudado entre os dois commits (ver git log entre eles)")
    da, db = _get(a, "acdt", "git", "dirty"), _get(b, "acdt", "git", "dirty")
    if da != db:
        add("acdt.git.dirty", da, db, "alto", "só uma das corridas tinha alterações não commitadas (ou o estado "
            "git é desconhecido num dos lados): o código usado pode ser diferente com o mesmo commit")
    elif da and db:
        ha, hb = _get(a, "acdt", "git", "dirty_diff_sha256"), _get(b, "acdt", "git", "dirty_diff_sha256")
        if ha != hb or ha is None:
            add("acdt.git.dirty_diff_sha256", ha, hb, "alto", "as duas corridas tinham alterações não commitadas "
                "diferentes (ou não identificadas): o código usado pode ser diferente")
    for lab, r in (("a", a), ("b", b)):
        dirty = _get(r, "acdt", "git", "dirty")
        if dirty:
            reprod.append(f"corrida {lab}: árvore suja — o commit sozinho não reproduz o resultado")
        elif dirty is None:
            reprod.append(f"corrida {lab}: estado git desconhecido (sem git ou pacote instalado)")
    if _get(a, "acdt", "version") != _get(b, "acdt", "version"):
        add("acdt.version", _get(a, "acdt", "version"), _get(b, "acdt", "version"), "medio", "versão do pacote diferente")
    for k in ("system", "machine"):
        va, vb = _get(a, "platform", k), _get(b, "platform", k)
        if va != vb:
            add(f"platform.{k}", va, vb, "alto", "SO/arquitectura diferente: compiladores, bibliotecas matemáticas e "
                "binários externos diferem (ex.: AVL Windows vs Linux difere no 3.º/4.º algarismo de CL/CD)")
    if _get(a, "platform", "release") != _get(b, "platform", "release") and \
            _get(a, "platform", "system") == _get(b, "platform", "system"):
        add("platform.release", _get(a, "platform", "release"), _get(b, "platform", "release"), "info",
            "versão do SO diferente (normalmente sem efeito nos números)")
    if _get(a, "python", "version") != _get(b, "python", "version"):
        add("python.version", _get(a, "python", "version"), _get(b, "python", "version"), "medio",
            "Python diferente: pode mudar a ordem de operações em bibliotecas e os arredondamentos")
    pa, pb = a.get("packages") or {}, b.get("packages") or {}
    for n in sorted(set(pa) | set(pb)):
        if pa.get(n) != pb.get(n):
            add(f"packages.{n}", pa.get(n), pb.get(n), "medio", f"versão de {n} diferente (ou ausente num dos lados)")
    ta, tb = a.get("tools") or {}, b.get("tools") or {}
    for n in sorted(set(ta) | set(tb)):
        xa, xb = ta.get(n), tb.get(n)
        if xa is None or xb is None:
            add(f"tools.{n}", bool(xa), bool(xb), "alto", f"{n} só foi usado numa das corridas: o caminho de cálculo "
                "foi diferente (ex.: recurso a um método de baixa fidelidade quando a ferramenta falta)")
            continue
        sa, sb = xa.get("sha256"), xb.get("sha256")
        if sa and sb and sa != sb:
            add(f"tools.{n}.sha256", sa[:12], sb[:12], "alto", f"binário de {n} diferente (outra compilação, versão "
                "ou plataforma): os últimos algarismos podem mudar — comparar só contra o mesmo binário")
        elif not sa or not sb:
            add(f"tools.{n}.sha256", sa, sb, "medio", f"identidade de {n} desconhecida num dos lados")
        if xa.get("version") != xb.get("version") and (xa.get("version") or xb.get("version")):
            add(f"tools.{n}.version", xa.get("version"), xb.get("version"), "alto", f"versão de {n} diferente")
        if xa.get("path") != xb.get("path"):
            add(f"tools.{n}.path", xa.get("path"), xb.get("path"), "info", "caminho diferente (só conta se o hash "
                "também mudar)")
    ia = {Path(str(x.get("path"))).name: x.get("sha256") for x in a.get("inputs") or []}
    ib = {Path(str(x.get("path"))).name: x.get("sha256") for x in b.get("inputs") or []}
    if sorted(ia.values(), key=str) != sorted(ib.values(), key=str):
        for n in sorted(set(ia) | set(ib)):
            if ia.get(n) != ib.get(n):
                add(f"inputs.{n}", (ia.get(n) or "")[:12] or None, (ib.get(n) or "")[:12] or None, "alto",
                    "entrada diferente (conteúdo canónico do YAML/JSON mudou, ou ficheiro só num dos lados)")
    if (a.get("seeds") or {}) != (b.get("seeds") or {}):
        add("seeds", a.get("seeds"), b.get("seeds"), "alto", "sementes aleatórias diferentes: amostragens "
            "(Monte Carlo, Sobol, DOE) dão números diferentes")
    if _get(a, "entry_point", "command") != _get(b, "entry_point", "command") or \
            _get(a, "entry_point", "argv") != _get(b, "entry_point", "argv"):
        add("entry_point", _get(a, "entry_point", "argv"), _get(b, "entry_point", "argv"), "medio",
            "comando ou opções diferentes (verificar se as opções mudam o cálculo)")
    ident = not any(d["peso"] in ("alto", "medio") for d in D)
    return {"identicos": ident, "reprodutivel": not reprod, "avisos_reprodutibilidade": reprod, "diferencas": D}


def explain(result: Mapping[str, Any]) -> str:
    """Texto pt-PT de :func:`compare`."""
    diffs = result.get("diferencas") or []
    if result.get("identicos"):
        head = "Mesma proveniência (código, plataforma, ferramentas, entradas e sementes)."
        if diffs:
            head += " Diferenças só informativas:"
        L = [head]
    else:
        L = ["Proveniência diferente — os resultados podem diferir por:"]
    for w in result.get("avisos_reprodutibilidade") or []:
        L.append(f"  [aviso] {w}")
    order = {"alto": 0, "medio": 1, "info": 2}
    for d in sorted(diffs, key=lambda x: order.get(str(x["peso"]), 3)):
        L.append(f"  [{d['peso']}] {d['campo']}: {d['a']!r} → {d['b']!r} — {d['porque']}")
    return "\n".join(L)
