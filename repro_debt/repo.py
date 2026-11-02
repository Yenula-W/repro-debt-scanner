"""Walk a repository and load the files the checks need."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .names import norm_dist

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".ipynb_checkpoints", ".venv", "venv", "env",
    ".env", ".tox", ".nox", "site-packages", "build", "dist", ".mypy_cache", ".pytest_cache", ".idea",
    ".vscode", ".eggs", "renv", "packrat",
}
MAX_CODE_BYTES = 2_000_000
MAX_NOTEBOOK_BYTES = 30_000_000

WORKFLOW_FILES = re.compile(
    r"^(Makefile|makefile|GNUmakefile|Snakefile|.*\.smk|dvc\.yaml|.*\.nf|nextflow\.config|.*\.cwl|.*\.wdl|"
    r"justfile|run_?all.*\.(sh|py|R)|reproduce.*\.(sh|py|R)|main\.(sh|R)|run\.sh|pipeline\.(sh|py|R)|"
    r"_targets\.R|workflow\.(sh|py|R))$",
    re.I,
)
LOCK_FILES = {
    "poetry.lock", "Pipfile.lock", "conda-lock.yml", "uv.lock", "pdm.lock", "renv.lock", "pixi.lock",
}


@dataclass
class Cell:
    index: Optional[int]  # 1-based notebook cell number; None for plain scripts
    source: str
    execution_count: Optional[int] = None
    outputs: list = field(default_factory=list)
    kind: str = "code"


@dataclass
class CodeUnit:
    path: str  # relative posix path
    lang: str  # python | r
    is_notebook: bool
    cells: List[Cell]
    nb_python_version: Optional[str] = None


@dataclass
class DepSpec:
    file: str
    names: Dict[str, int] = field(default_factory=dict)  # normalized name -> line
    unpinned: List[Tuple[str, int]] = field(default_factory=list)
    python_version: bool = False


@dataclass
class Repo:
    root: Path
    files: List[str] = field(default_factory=list)  # all relative posix paths
    units: List[CodeUnit] = field(default_factory=list)
    readme_path: Optional[str] = None
    readme: str = ""
    deps: List[DepSpec] = field(default_factory=list)
    has_lock: bool = False
    python_version_recorded: bool = False
    workflow_files: List[str] = field(default_factory=list)
    local_modules: Set[str] = field(default_factory=set)
    license_found: bool = False

    @property
    def declared(self) -> Set[str]:
        out: Set[str] = set()
        for d in self.deps:
            out.update(d.names)
        return out

    def exists(self, rel: str) -> bool:
        return (self.root / rel).exists()


def _read(p: Path, limit: int = MAX_CODE_BYTES) -> Optional[str]:
    try:
        if p.stat().st_size > limit:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def load_repo(root: str) -> Repo:
    rootp = Path(root).resolve()
    repo = Repo(root=rootp)
    for dirpath, dirnames, filenames in os.walk(rootp):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        rel_dir = Path(dirpath).relative_to(rootp)
        if "__init__.py" in filenames and str(rel_dir) != ".":
            repo.local_modules.add(rel_dir.name)
        for fn in sorted(filenames):
            rel = (rel_dir / fn).as_posix()
            repo.files.append(rel)
    for rel in repo.files:
        _classify(repo, rel)
    repo.python_version_recorded = repo.python_version_recorded or any(d.python_version for d in repo.deps)
    return repo


def _classify(repo: Repo, rel: str) -> None:
    p = repo.root / rel
    name = p.name
    lower = name.lower()
    depth = rel.count("/")
    if lower.endswith(".py"):
        repo.local_modules.add(p.stem)
        src = _read(p)
        if src is not None:
            repo.units.append(CodeUnit(rel, "python", False, [Cell(None, src)]))
        if name == "setup.py" and src:
            _parse_setup_py(repo, rel, src)
    elif lower.endswith(".ipynb"):
        unit = _load_notebook(p, rel)
        if unit:
            repo.units.append(unit)
    elif lower.endswith(".r") or lower.endswith(".rmd"):
        src = _read(p)
        if src is not None:
            if lower.endswith(".rmd"):
                src = _rmd_to_r(src)
            repo.units.append(CodeUnit(rel, "r", False, [Cell(None, src)]))

    if depth == 0 and re.match(r"readme(\.(md|rst|txt|markdown))?$", lower):
        if not repo.readme_path or lower.startswith("readme.md"):
            repo.readme_path = rel
            repo.readme = _read(p) or ""
    if depth <= 1 and re.match(r"(license|licence|copying)(\..*)?$", lower):
        repo.license_found = True
    if name in LOCK_FILES:
        repo.has_lock = True
        if name == "renv.lock":
            repo.deps.append(DepSpec(rel, python_version=True))
            _parse_renv_lock(repo.deps[-1], _read(p) or "")
    if WORKFLOW_FILES.match(name):
        repo.workflow_files.append(rel)
    if depth <= 2 and re.match(r"requirements.*\.(txt|in)$", lower) or (
        rel.lower().startswith("requirements/") and lower.endswith(".txt")
    ):
        repo.deps.append(_parse_requirements(rel, _read(p) or ""))
    elif re.match(r"(environment|env|conda).*\.ya?ml$", lower) and depth <= 2:
        repo.deps.append(_parse_env_yml(rel, _read(p) or ""))
    elif name == "pyproject.toml":
        _parse_pyproject(repo, rel, _read(p) or "")
    elif name == "setup.cfg":
        _parse_setup_cfg(repo, rel, _read(p) or "")
    elif name == "Pipfile":
        _parse_pipfile(repo, rel, _read(p) or "")
    elif name == "DESCRIPTION" and depth <= 1:
        _parse_description(repo, rel, _read(p) or "")
    elif name == "Dockerfile" or lower.endswith(".dockerfile"):
        _parse_dockerfile(repo, rel, _read(p) or "")
    elif name in (".python-version", "runtime.txt"):
        repo.python_version_recorded = True


def _rmd_to_r(src: str) -> str:
    """Keep R chunks, blank out prose (keeps line numbers)."""
    out, in_chunk = [], False
    for line in src.splitlines():
        if re.match(r"^```\{r", line):
            in_chunk = True
            out.append("")
        elif in_chunk and line.startswith("```"):
            in_chunk = False
            out.append("")
        else:
            out.append(line if in_chunk else "")
    return "\n".join(out)


def _load_notebook(p: Path, rel: str) -> Optional[CodeUnit]:
    raw = _read(p, MAX_NOTEBOOK_BYTES)
    if raw is None:
        return None
    try:
        nb = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(nb, dict):
        return None
    meta = nb.get("metadata") or {}
    lang = ((meta.get("kernelspec") or {}).get("language") or (meta.get("language_info") or {}).get("name") or "python")
    lang = "r" if str(lang).lower() == "r" else "python"
    cells = []
    for i, c in enumerate(nb.get("cells") or [], start=1):
        if not isinstance(c, dict):
            continue
        src = c.get("source", "")
        if isinstance(src, list):
            src = "".join(src)
        cells.append(Cell(i, src, c.get("execution_count"), c.get("outputs") or [], c.get("cell_type", "code")))
    ver = (meta.get("language_info") or {}).get("version")
    return CodeUnit(rel, lang, True, cells, nb_python_version=ver)


REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._\-]*)(\[[^\]]*\])?\s*(.*)$")


def _is_pinned(spec: str) -> bool:
    spec = spec.split(";")[0].strip()
    return bool(re.search(r"(===?|~=)\s*[0-9]", spec)) or "@" in spec


def _parse_requirements(rel: str, text: str) -> DepSpec:
    d = DepSpec(rel)
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split(" #")[0].strip()
        if not line or line.startswith(("#", "-")):
            continue
        if "://" in line or line.startswith((".", "/")):
            m = re.search(r"#egg=([A-Za-z0-9._\-]+)", line)
            if m:
                d.names[norm_dist(m.group(1))] = n
            continue
        m = REQ_LINE.match(line)
        if not m:
            continue
        name, spec = m.group(1), m.group(3)
        d.names[norm_dist(name)] = n
        if not _is_pinned(spec):
            d.unpinned.append((name, n))
    return d


def _parse_env_yml(rel: str, text: str) -> DepSpec:
    d = DepSpec(rel)
    in_deps = False
    for n, line in enumerate(text.splitlines(), 1):
        if re.match(r"^dependencies\s*:", line):
            in_deps = True
            continue
        if in_deps and re.match(r"^\S", line):
            in_deps = False
        if not in_deps:
            continue
        m = re.match(r"^\s*-\s*([^\s:#]+)\s*(.*)$", line)
        if not m:
            continue
        item = (m.group(1) + " " + m.group(2)).split("#")[0].strip()
        if item.endswith(":"):  # "- pip:"
            continue
        name = re.split(r"[=<>!~ ]", item, 1)[0]
        if "::" in name:
            name = name.split("::", 1)[1]
        if not name:
            continue
        if name.lower() == "python":
            d.python_version = bool(re.search(r"[=<>]", item))
            continue
        if name.lower() == "pip":
            continue
        d.names[norm_dist(name)] = n
        rest = item[len(name):]
        if not re.search(r"=\s*[0-9]", rest):
            d.unpinned.append((name, n))
    return d


def _quoted_reqs(block: str) -> List[str]:
    return re.findall(r"""["']([A-Za-z0-9][^"']*)["']""", block)


def _add_reqs(d: DepSpec, reqs: List[str], line: int) -> None:
    for r in reqs:
        m = REQ_LINE.match(r)
        if not m:
            continue
        d.names[norm_dist(m.group(1))] = line
        if not _is_pinned(m.group(3)):
            d.unpinned.append((m.group(1), line))


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _parse_pyproject(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    if re.search(r"^\s*(requires-python|python)\s*=", text, re.M):
        d.python_version = True
    m = re.search(r"^\s*dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M)
    if m:
        _add_reqs(d, _quoted_reqs(m.group(1)), _line_of(text, m.start()))
    for m in re.finditer(r"^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)", text, re.S | re.M):
        for r in _quoted_reqs(m.group(1)):
            rm = REQ_LINE.match(r)
            if rm:
                d.names.setdefault(norm_dist(rm.group(1)), _line_of(text, m.start()))
    m = re.search(r"^\[tool\.poetry\.dependencies\](.*?)(?=^\[|\Z)", text, re.S | re.M)
    if m:
        for lm in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.+)$", m.group(1), re.M):
            name = lm.group(1)
            if name.lower() == "python":
                d.python_version = True
                continue
            line = _line_of(text, m.start(1) + lm.start())
            d.names[norm_dist(name)] = line
            if not re.search(r"""["']=?=?\s*[0-9]""", lm.group(2)) or re.search(r"[\^~>*]", lm.group(2)):
                d.unpinned.append((name, line))
    m = re.search(r"^\s*name\s*=\s*[\"']([^\"']+)", text, re.M)
    if m:
        repo.local_modules.add(m.group(1).replace("-", "_"))
    if d.names or d.python_version:
        repo.deps.append(d)


def _parse_setup_py(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    if "python_requires" in text:
        d.python_version = True
    m = re.search(r"install_requires\s*=\s*\[(.*?)\]", text, re.S)
    if m:
        _add_reqs(d, _quoted_reqs(m.group(1)), _line_of(text, m.start()))
    m = re.search(r"\bname\s*=\s*[\"']([^\"']+)", text)
    if m:
        repo.local_modules.add(m.group(1).replace("-", "_"))
    if d.names or d.python_version or m:
        repo.deps.append(d)


def _parse_setup_cfg(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    if "python_requires" in text:
        d.python_version = True
    m = re.search(r"install_requires\s*=\s*\n((?:[ \t]+\S.*\n?)+)", text)
    if m:
        line = _line_of(text, m.start())
        _add_reqs(d, [x.strip() for x in m.group(1).splitlines() if x.strip()], line)
    if d.names or d.python_version:
        repo.deps.append(d)


def _parse_pipfile(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    if "python_version" in text:
        d.python_version = True
    for sec in re.finditer(r"^\[(dev-)?packages\](.*?)(?=^\[|\Z)", text, re.S | re.M):
        for lm in re.finditer(r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*(.+)$", sec.group(2), re.M):
            line = _line_of(text, sec.start(2) + lm.start())
            d.names[norm_dist(lm.group(1))] = line
            if not re.search(r"""["']==\s*[0-9]""", lm.group(2)):
                d.unpinned.append((lm.group(1), line))
    repo.deps.append(d)


def _parse_description(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    for field_ in ("Depends", "Imports", "Suggests", "LinkingTo"):
        m = re.search(rf"^{field_}:\s*(.*?)(?=^\S|\Z)", text, re.S | re.M)
        if not m:
            continue
        line = _line_of(text, m.start())
        for item in m.group(1).split(","):
            item = item.strip()
            name = re.split(r"[\s(]", item, 1)[0]
            if not name:
                continue
            if name == "R":
                d.python_version = True
                continue
            d.names[norm_dist(name)] = line
            if "==" not in item:
                d.unpinned.append((name, line))
    if re.search(r"^License:", text, re.M):
        repo.license_found = True
    repo.deps.append(d)


def _parse_renv_lock(d: DepSpec, text: str) -> None:
    try:
        data = json.loads(text)
    except ValueError:
        return
    for name in (data.get("Packages") or {}):
        d.names[norm_dist(name)] = 1


def _parse_dockerfile(repo: Repo, rel: str, text: str) -> None:
    d = DepSpec(rel)
    if re.search(r"^FROM\s+\S*(python|r-base|rocker/\S+):[0-9]", text, re.M | re.I):
        d.python_version = True
    for m in re.finditer(r"(?:pip3?|conda|mamba)\s+install\s+([^\n&|;]+)", text):
        line = _line_of(text, m.start())
        for tok in m.group(1).split():
            if tok.startswith("-") or tok in ("\\", ".") or "/" in tok or re.search(r"\.(txt|ya?ml|toml|cfg)$", tok):
                continue
            rm = REQ_LINE.match(tok.strip("'\""))
            if rm:
                d.names[norm_dist(rm.group(1))] = line
                if not _is_pinned(rm.group(3)):
                    d.unpinned.append((rm.group(1), line))
    repo.deps.append(d)
