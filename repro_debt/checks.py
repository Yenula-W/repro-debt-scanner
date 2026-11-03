"""Turn per-file facts into findings and per-step runnability."""
from __future__ import annotations

import glob
import posixpath
import re
import tarfile
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .analyze import ABS_PATH, UnitFacts, analyze_unit, norm_rel
from .model import Finding, Step
from .names import BUILTINS, R_BASE, STDLIB, import_candidates, norm_dist
from .repo import Repo

FIG_DIR = re.compile(r"(^|/)(fig|figs|figures?|plots?|results?|outputs?|images?)/", re.I)
FIG_EXT = re.compile(r"\.(png|pdf|svg|jpe?g|tiff?|eps)$", re.I)
RUN_INSTRUCTIONS = re.compile(
    r"```|^\s{4}\S|^\.\. code|python3?\s+\S+\.py|jupyter|pip install|conda (env )?create|\bmake\b|snakemake|"
    r"Rscript|R CMD|source\(|^#+\s*(usage|how to (run|use|reproduce)|running|reproduc|getting started|"
    r"quick ?start|installation|instructions)",
    re.I | re.M,
)
DATA_NOTE = re.compile(
    r"data availab|zenodo|figshare|dryad|osf\.io|doi\.org|\b10\.\d{4,}/|download (the )?(raw )?data|"
    r"data (is|are|can be) (available|found|obtained|downloaded)|dataset (is|are) available|access the data|"
    r"data (sources?|access)|obtain the data|kaggle|physionet|openneuro|gene expression omnibus|\bgeo\b|"
    r"\bsra\b|synapse\.org|huggingface\.co/datasets|data/README",
    re.I,
)
ERROR_CLASS = {
    "ModuleNotFoundError": "dependency", "ImportError": "dependency", "PackageNotFoundError": "dependency",
    "FileNotFoundError": "data", "OSError": "data", "IOError": "data", "EmptyDataError": "data",
    "ParserError": "data", "PermissionError": "data", "HTTPError": "data", "URLError": "data",
    "KeyError": "data",
}
TEST_FILE = re.compile(r"/(tests?|testthat)/|/test_[^/]*$|_test\.(py|R)$", re.I)
# package docs, test snapshots and illustrations are not results
NOT_RESULT_FIG = re.compile(r"/(man|tests?|docs?|pkgdown|vignettes|\.github|assets?|static)/|"
                            r"(logo|banner|icon|hex|sticker|framework|overview|concept|schematic|diagram|"
                            r"workflow|pipeline|graphical.?abstract|screenshot|architecture|overall)[^/]*$", re.I)
FIG_WRITE_HINT = re.compile(r"savefig|imwrite|imsave|write_image|ggsave|png\(|pdf\(")


@dataclass
class ScanResult:
    repo: Repo
    findings: List[Finding] = field(default_factory=list)
    steps: List[Step] = field(default_factory=list)
    facts: List[UnitFacts] = field(default_factory=list)


def run_checks(repo: Repo) -> ScanResult:
    res = ScanResult(repo)
    res.facts = [analyze_unit(u) for u in repo.units]
    f = res.findings
    _deps(repo, res.facts, f)
    _paths_and_data(repo, res.facts, f)
    _randomness(repo, res.facts, f)
    _notebooks(res.facts, f)
    _figures(repo, res.facts, f)
    _docs(repo, res.facts, f)
    res.steps = _steps(repo, res.facts, f)
    return res


# ------------------------------------------------------------------ dependencies

def _local_names(repo: Repo) -> Set[str]:
    local = set(repo.local_modules)
    for rel in repo.files:
        if rel.endswith(".py"):
            parts = rel.split("/")[:-1]
            local.update(parts)
    return local


def _third_party_imports(repo: Repo, facts: List[UnitFacts]) -> "OrderedDict[Tuple[str, str], Tuple[str, Optional[int], int]]":
    """(lang, module) -> first (file, cell, line)."""
    local = _local_names(repo)
    out: "OrderedDict[Tuple[str, str], Tuple[str, Optional[int], int]]" = OrderedDict()
    for fa in facts:
        if re.match(r"readme\.", posixpath.basename(fa.unit.path), re.I):
            continue  # README.Rmd shows install commands (remotes::install_github), not dependencies
        for ref in fa.imports:
            mod = ref.path
            if fa.unit.lang == "python":
                if mod in STDLIB or mod in local or mod.startswith("_"):
                    continue
            else:
                if mod in R_BASE or mod in local:
                    continue
            out.setdefault((fa.unit.lang, mod), (fa.unit.path, ref.cell, ref.line))
    return out


def _deps(repo: Repo, facts: List[UnitFacts], f: List[Finding]) -> None:
    if not repo.units:
        return
    imports = _third_party_imports(repo, facts)
    declared = repo.declared
    langs = {u.lang for u in repo.units}
    if not repo.deps:
        mods = sorted({m for (_, m) in imports})
        shown = ", ".join(mods[:8]) + (f" and {len(mods) - 8} more" if len(mods) > 8 else "")
        f.append(Finding("DEP001", "No requirements.txt, environment.yml, pyproject.toml, DESCRIPTION or lock file "
                         "found; nobody can tell which packages to install."
                         + (f" The code imports: {shown}." if mods else ""), detail=shown or None))
    else:
        for (lang, mod), (path, cell, line) in imports.items():
            cands = import_candidates(mod) if lang == "python" else [norm_dist(mod)]
            if mod in ("setuptools", "distutils") and posixpath.basename(path) == "setup.py":
                continue  # build tooling, installed by pip itself
            if not any(c in declared for c in cands):
                f.append(Finding("DEP003", f"`{mod}` is imported but not listed in any dependency file "
                                 f"({', '.join(d.file for d in repo.deps[:3])}).", path, line, cell, detail=mod))
        if not repo.has_lock:
            for d in repo.deps:
                # R packages state minimum versions in DESCRIPTION by convention; docs/ deps don't affect results
                # Exact pins belong in requirements/environment files. Package metadata (DESCRIPTION, pyproject,
                # setup.py) states ranges by convention; dev/test/docs/CI requirement files don't affect results.
                base = posixpath.basename(d.file)
                if base in ("DESCRIPTION", "pyproject.toml", "setup.py", "setup.cfg") or d.file.startswith(
                        ("docs/", "doc/")) or re.search(r"dev|test|doc|lint|ci\b|gh-action|mypy|build", base, re.I):
                    continue
                if d.unpinned:
                    names = list(OrderedDict.fromkeys(n for n, _ in d.unpinned))
                    shown = ", ".join(names[:6]) + (f" (+{len(names) - 6} more)" if len(names) > 6 else "")
                    f.append(Finding("DEP002", f"{len(names)} of {len(d.names)} packages in {d.file} have no exact "
                                     f"version: {shown}.", d.file, d.unpinned[0][1], detail=d.file))
    if not repo.python_version_recorded:
        nb_versions = sorted({u.nb_python_version for u in repo.units if u.nb_python_version})
        which = "Python" if "python" in langs else "R"
        extra = (f" (notebook metadata says {', '.join(nb_versions[:3])}, but that is not an installable spec)"
                 if nb_versions else "")
        f.append(Finding("ENV001", f"The {which} version used is not recorded anywhere{extra}."))


# ------------------------------------------------------------------ paths / data / workflow

def _candidates(unit_path: str, p: str) -> List[str]:
    base = posixpath.dirname(unit_path)
    c = [norm_rel("", p)]
    if base:
        c.append(norm_rel(base, p))
    return [x for x in c if not x.startswith("../")] or c


def _suffixes(repo: Repo) -> Set[str]:
    """Every contiguous run of path segments of every file (so directories match too)."""
    cached = getattr(repo, "_suffix_cache", None)
    if cached is None:
        cached = set()
        for rel in repo.files + _archive_members(repo):
            parts = rel.split("/")
            for i in range(len(parts)):
                for j in range(i + 1, len(parts) + 1):
                    cached.add("/".join(parts[i:j]))
        repo._suffix_cache = cached  # type: ignore[attr-defined]
    return cached


DEPOSIT = re.compile(r"zenodo\.org|figshare\.com|osf\.io|datadryad\.org|dataverse|ebi\.ac\.uk/biostudies", re.I)


def _archive_members(repo: Repo) -> List[str]:
    """Files bundled in a zip/tar in the repo (e.g. `unzip data.zip` in the README) count as present."""
    out: List[str] = []
    for rel in repo.files:
        lower = rel.lower()
        path = str(repo.root / rel)
        base = posixpath.dirname(rel)
        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(path) as z:
                    names = z.namelist()
            elif lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
                with tarfile.open(path) as t:
                    names = t.getnames()
            else:
                continue
        except (OSError, zipfile.BadZipFile, tarfile.TarError, EOFError):
            continue  # LFS pointer, partial clone or corrupt archive
        out.extend(posixpath.join(base, n).lstrip("./") if base else n.lstrip("./") for n in names)
    return out


def _doc_text(repo: Repo) -> str:
    """README plus shell scripts and Makefiles: places that document how inputs get created."""
    cached = getattr(repo, "_doc_cache", None)
    if cached is None:
        parts = [repo.readme]
        for rel in repo.files:
            name = posixpath.basename(rel)
            if rel.endswith((".sh", ".bash")) or name in ("Makefile", "Snakefile", "justfile"):
                try:
                    parts.append((repo.root / rel).read_text(encoding="utf-8", errors="replace")[:200_000])
                except OSError:
                    pass
        cached = "\n".join(parts)
        repo._doc_cache = cached  # type: ignore[attr-defined]
    return cached


def _documented(repo: Repo, p: str) -> bool:
    tail = re.sub(r"^(\./|\.\./)+", "", p).rstrip("/")
    if not tail:
        return False
    doc = _doc_text(repo)
    top = tail.split("/")[0]
    return tail in doc or ("/" in tail and re.search(r"(?<![\w.-])" + re.escape(top) + r"/", doc) is not None)


def _exists(repo: Repo, cands: List[str]) -> bool:
    # Scripts often run from another working directory (R vignettes, notebooks in subfolders), so a
    # relative path that matches the tail of any file in the repo counts as present.
    suffixes = _suffixes(repo)
    for c in cands:
        tail = re.sub(r"^(\.\./)+", "", c).rstrip("/")
        if tail in suffixes:
            return True
    for c in cands:
        if any(ch in c for ch in "*?["):
            if glob.glob(str(repo.root / c)):
                return True
            continue
        if (repo.root / c).exists():
            return True
    return False


def _paths_and_data(repo: Repo, facts: List[UnitFacts], f: List[Finding]) -> None:
    seen_abs: Set[Tuple[str, str]] = set()
    for fa in facts:
        for ref in fa.abs_paths:
            if re.match(r"^~/[^/]+/?$", ref.path):
                continue  # `~/some_output` is created on any machine; only deeper home paths are author-specific
            key = (fa.unit.path, ref.path)
            if key in seen_abs:
                continue
            seen_abs.add(key)
            f.append(Finding("PATH001", f"Absolute path `{ref.path}` only exists on the author's machine.",
                             fa.unit.path, ref.line, ref.cell, detail=ref.path))

    produced: Dict[str, str] = {}  # normalized path or basename -> producing file
    produced_dirs: List[str] = []  # folders a tool was told to write into (output_dir=...)
    for fa in facts:
        for ref in fa.writes:
            if ref.path.endswith("/*"):
                produced_dirs += [c[:-2] for c in _candidates(fa.unit.path, ref.path)]
                continue
            if ABS_PATH.match(ref.path):
                continue
            for c in _candidates(fa.unit.path, ref.path):
                produced.setdefault(c, fa.unit.path)
            produced.setdefault("#" + posixpath.basename(ref.path), fa.unit.path)

    workflow_doc = bool(repo.workflow_files)
    seen_missing: Set[str] = set()
    for fa in facts:
        for ref in fa.reads:
            p = ref.path
            if ABS_PATH.match(p) or "{" in p or "%" in p or p.startswith("<"):
                continue
            cands = _candidates(fa.unit.path, p)
            if _exists(repo, cands):
                continue
            producer = next((produced[c] for c in cands if c in produced), None) or produced.get(
                "#" + posixpath.basename(p))
            fa_key = cands[0]
            if producer == fa.unit.path:
                continue
            if producer:
                fa_rec = (fa.unit.path, producer)
                setattr(ref, "producer", producer)
                if workflow_doc or posixpath.basename(producer) in repo.readme:
                    continue
                if ("WF", fa_rec) in seen_missing:
                    continue
                seen_missing.add(("WF", fa_rec))  # type: ignore[arg-type]
                f.append(Finding("WF001", f"Reads `{p}`, which is created by `{producer}`, but nothing says "
                                 f"`{producer}` must run first.", fa.unit.path, ref.line, ref.cell,
                                 detail=f"{producer} -> {fa.unit.path}"))
                continue
            if any(c.startswith(d + "/") for c in cands for d in produced_dirs):
                continue
            if fa_key in seen_missing or _documented(repo, p):
                continue
            seen_missing.add(fa_key)
            deposit = DEPOSIT.search(repo.readme)
            f.append(Finding("DATA001", f"Reads `{p}`, which is not in the repository and no script creates it."
                             + (f" The README links a data deposit ({deposit.group(0)}): check this file is in it "
                                "and say where to put it." if deposit else ""),
                             fa.unit.path, ref.line, ref.cell, detail=p))


# ------------------------------------------------------------------ randomness

def _randomness(repo: Repo, facts: List[UnitFacts], f: List[Finding]) -> None:
    files = set(repo.files)
    for fa in facts:
        path = fa.unit.path
        in_package = posixpath.join(posixpath.dirname(path), "__init__.py") in files
        main_guard = "__main__" in "".join(c.source for c in fa.unit.cells)
        if TEST_FILE.search("/" + path) or (fa.unit.lang == "python" and in_package and not main_guard):
            continue  # seeds belong in the scripts/notebooks that run, not in tests or importable library code
        if fa.random_uses and not fa.has_seed:
            first = fa.random_uses[0]
            kinds = sorted({r.path.split("(")[0] for r in fa.random_uses})[:4]
            f.append(Finding("RAND001", f"Uses randomness ({', '.join(kinds)}; {len(fa.random_uses)} call(s)) "
                             "but never sets a seed, so results change on every run.",
                             fa.unit.path, first.line, first.cell, detail=fa.unit.path))


# ------------------------------------------------------------------ notebooks

def _notebooks(facts: List[UnitFacts], f: List[Finding]) -> None:
    for fa in facts:
        u = fa.unit
        if not u.is_notebook:
            continue
        code = [c for c in u.cells if c.kind == "code"]
        counts = [(c.index, c.execution_count) for c in code if isinstance(c.execution_count, int)]
        out_of_order = False
        for (pi, pc), (ci, cc) in zip(counts, counts[1:]):
            if cc <= pc:
                out_of_order = True
                how = "has the same run number as" if cc == pc else "was executed before"
                f.append(Finding("NB001", f"Cell {ci} (run #{cc}) {how} cell {pi} (run #{pc}) above it; "
                                 "the saved results came from running cells out of order.", u.path, None, ci,
                                 detail=u.path))
                break

        # name flow
        if u.lang == "python":
            all_defs: Dict[str, int] = {}
            for idx, defs, _, _ in fa.cell_flow:
                for d in defs:
                    all_defs.setdefault(d, idx)
            later_defs: Dict[str, List[int]] = {}
            for idx, defs, _, _ in fa.cell_flow:
                for d in defs:
                    later_defs.setdefault(d, []).append(idx)
            defined: Set[str] = set()
            star = False
            reported: Set[str] = set()
            n_reported = 0
            for idx, defs, uses, cell_star in fa.cell_flow:
                star = star or cell_star
                for name, line in uses:
                    if name in defined or name in defs or name in BUILTINS or name in reported:
                        continue
                    if n_reported >= 10:
                        break
                    later = [j for j in later_defs.get(name, []) if j > idx]
                    if later:
                        reported.add(name)
                        n_reported += 1
                        f.append(Finding("NB002", f"Cell {idx} uses `{name}`, which is only defined later in cell "
                                         f"{later[0]}; this only worked because of hidden kernel state.",
                                         u.path, line, idx, detail=f"{posixpath.basename(u.path)}:{name}"))
                    elif not star and name not in later_defs:
                        reported.add(name)
                        n_reported += 1
                        f.append(Finding("NB003", f"Cell {idx} uses `{name}`, which is never defined or imported "
                                         "in this notebook.", u.path, line, idx,
                                         detail=f"{posixpath.basename(u.path)}:{name}"))
                defined |= defs

        # saved errors
        for c in code:
            for o in c.outputs:
                if isinstance(o, dict) and o.get("output_type") == "error":
                    ename = str(o.get("ename") or "Error")
                    cls = ERROR_CLASS.get(ename, "code")
                    if ename == "KeyboardInterrupt":
                        msg = f"Cell {c.index} was saved after being interrupted, so its saved output is incomplete."
                    else:
                        msg = (f"Cell {c.index} was saved showing `{ename}: {str(o.get('evalue', ''))[:80]}` "
                               f"(looks like a {cls} problem).")
                    f.append(Finding("NB005", msg, u.path, None, c.index, detail=f"{u.path} ({ename})", category=cls))
                    break

        # non-linear outputs
        has_outputs = any(c.outputs for c in code)
        if has_outputs and not out_of_order and counts:
            nums = [cc for _, cc in counts]
            executed_idx = {ci for ci, _ in counts}
            skipped = [c.index for c in code if c.index not in executed_idx and c.source.strip()]
            gaps = nums[0] != 1 or any(b - a != 1 for a, b in zip(nums, nums[1:]))
            if gaps or skipped:
                why = []
                if nums[0] != 1:
                    why.append(f"the first run number is {nums[0]}, not 1")
                elif gaps:
                    why.append("run numbers skip (cells were re-run or deleted)")
                if skipped:
                    why.append(f"{len(skipped)} code cell(s) were never run")
                f.append(Finding("NB004", "Saved outputs did not come from a clean top-to-bottom run: "
                                 + "; ".join(why) + ".", u.path, None, None, detail=u.path))


# ------------------------------------------------------------------ figures

def _figures(repo: Repo, facts: List[UnitFacts], f: List[Finding]) -> None:
    figs = [p for p in repo.files if FIG_EXT.search(p) and FIG_DIR.search("/" + p)
            and not NOT_RESULT_FIG.search("/" + p) and posixpath.basename(p) not in repo.readme]  # README art
    if not figs:
        return
    if any(fa.unresolved_writes for fa in facts):
        return  # some outputs have computed names; can't tell which figures are generated
    written = {posixpath.basename(r.path) for fa in facts for r in fa.writes}
    written_stems = {posixpath.splitext(w)[0] for w in written}
    orphans = [p for p in figs if posixpath.basename(p) not in written
               and posixpath.splitext(posixpath.basename(p))[0] not in written_stems]
    if orphans:
        shown = ", ".join(orphans[:4]) + (f" (+{len(orphans) - 4} more)" if len(orphans) > 4 else "")
        f.append(Finding("FIG001", f"{len(orphans)} figure/result file(s) have no code in the repo that writes "
                         f"them: {shown}.", orphans[0], detail=shown))


# ------------------------------------------------------------------ docs

def _docs(repo: Repo, facts: List[UnitFacts], f: List[Finding]) -> None:
    if not repo.readme_path:
        f.append(Finding("DOC001", "There is no README at the top of the repository."))
    elif not RUN_INSTRUCTIONS.search(repo.readme):
        f.append(Finding("DOC002", "The README does not show any commands for installing or running the code.",
                         repo.readme_path))
    if not repo.license_found:
        f.append(Finding("DOC003", "No LICENSE file found; by default nobody may legally reuse this code."))
    reads_data = any(x.check == "DATA001" for x in f)  # only matters when some input is not in the repo
    has_data_readme = any(re.match(r"data/readme", p, re.I) for p in repo.files)
    if reads_data and not has_data_readme and not DATA_NOTE.search(repo.readme):
        f.append(Finding("DOC004", "The code reads data files but the README does not say where the data comes "
                         "from or how to get it.", repo.readme_path))


# ------------------------------------------------------------------ steps (partial reproducibility)

def _steps(repo: Repo, facts: List[UnitFacts], findings: List[Finding]) -> List[Step]:
    by_file: Dict[str, List[Finding]] = {}
    for x in findings:
        if x.file:
            by_file.setdefault(x.file, []).append(x)
    no_deps = any(x.check == "DEP001" for x in findings)
    steps = []
    for fa in facts:
        if not fa.is_entrypoint:
            continue
        s = Step(fa.unit.path)
        cats: List[str] = []
        error_cls: Optional[str] = None
        for x in by_file.get(fa.unit.path, []):
            if x.check == "DATA001":
                s.reasons.append(f"missing input `{x.detail}`")
                cats.append("data")
            elif x.check == "PATH001":
                s.reasons.append(f"absolute path `{x.detail}`")
                cats.append("data")
            elif x.check == "DEP003":
                s.reasons.append(f"undeclared package `{x.detail}`")
                cats.append("dependency")
            elif x.check in ("NB002", "NB003"):
                s.reasons.append(f"hidden-state name `{x.detail.split(':', 1)[-1]}`")
                cats.append("code")
            elif x.check == "NB005":
                s.reasons.append("saved error " + x.message.split(" was saved showing ")[-1].split(" (looks like")[0])
                error_cls = error_cls or x.category
                cats.append(x.category)
            elif x.check == "WF001":
                pass
        if no_deps and any(r.path not in STDLIB for r in fa.imports):
            s.reasons.append("no dependency file")
            cats.append("dependency")
        for fs in fa.syntax_errors:
            s.reasons.append(f"cell {fs.cell} does not parse" if fs.cell else "file does not parse")
            cats.append("code")
        for ref in fa.reads:
            prod = getattr(ref, "producer", None)
            if prod and prod != fa.unit.path and prod not in s.upstream:
                s.upstream.append(prod)
        if cats:
            s.status = "blocked"
            if error_cls:
                s.likely_break = error_cls
            else:
                for c in ("data", "dependency", "code"):
                    if c in cats:
                        s.likely_break = c
                        break
        elif s.upstream:
            s.status = "needs-upstream"
        steps.append(s)
    return steps
