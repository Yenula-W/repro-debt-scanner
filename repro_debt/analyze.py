"""Per-file static analysis: imports, paths, file reads/writes, randomness, name flow."""
from __future__ import annotations

import ast
import os
import posixpath
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .repo import Cell, CodeUnit

ABS_PATH = re.compile(
    r"^(?:/Users/|/home/|/mnt/|/media/|/Volumes/|/scratch/|/gpfs/|/storage/|/data/|/projects?/|/net/|/nfs/|"
    r"/work/|/lustre/|/cluster/|/n/|/groups?/|/srv/|/opt/data|~/|[A-Za-z]:[\\/])"
)

READERS = {
    "read_csv", "read_table", "read_excel", "read_parquet", "read_json", "read_pickle", "read_hdf", "read_feather",
    "read_fwf", "read_stata", "read_sas", "read_spss", "read_orc", "loadtxt", "genfromtxt", "load", "fromfile",
    "open_dataset", "open_mfdataset", "open_dataarray", "open_zarr", "imread", "loadmat", "read_image",
    "load_workbook", "read_file", "read_h5ad", "read_10x_h5", "read_10x_mtx", "read_loom", "read_raw_fif",
    "read_raw_edf", "read_epochs", "read_shapefile", "read_gbq", "read_sql", "read_xml", "read_mat",
    "read_tiff", "imopen", "read_text", "read_bytes", "File", "open",
}
# Reader names that also exist on objects as non-file operations; require the arg to look like a path.
WRITERS = {
    "to_csv", "to_excel", "to_parquet", "to_pickle", "to_hdf", "to_feather", "to_json", "to_netcdf", "to_zarr",
    "to_stata", "to_file", "savefig", "save", "savez", "savez_compressed", "savetxt", "imwrite", "imsave",
    "write_h5ad", "dump", "savemat", "write_text", "write_bytes", "to_html", "to_latex", "write_image",
    "write_html", "save_model", "save_weights",
}
PATH_KWS = {"path", "fname", "filename", "file", "filepath", "filepath_or_buffer", "path_or_buf", "fp", "f",
            "io", "uri", "filename_or_obj", "paths", "store", "fn"}
FILE_EXT = re.compile(r"\.[A-Za-z0-9]{1,6}$")

R_READERS = r"(?:read\.csv2?|read\.table|read\.delim|read_csv|read_tsv|read_delim|read_excel|read_xlsx|readRDS|read_rds|fread|load|readLines|read\.xlsx|st_read|read_sf|readr::read_csv|read_feather|read_parquet|raster|rast|readxl::read_excel|vroom|import)"
R_WRITERS = r"(?:write\.csv2?|write\.table|write_csv|write_tsv|saveRDS|write_rds|fwrite|save|ggsave|png|pdf|svg|tiff|jpeg|writeLines|write\.xlsx|write_xlsx|st_write|write_feather|write_parquet|export)"

RANDOM_NP = {"rand", "randn", "randint", "random", "choice", "shuffle", "permutation", "normal", "uniform",
             "binomial", "poisson", "beta", "gamma", "exponential", "multivariate_normal", "random_sample",
             "standard_normal", "lognormal", "dirichlet", "multinomial"}
RANDOM_STDLIB = {"random", "randint", "choice", "choices", "shuffle", "sample", "uniform", "gauss", "randrange",
                 "normalvariate", "betavariate", "expovariate"}
RANDOM_TORCH = {"rand", "randn", "randint", "randperm", "rand_like", "randn_like", "normal", "bernoulli",
                "multinomial"}
SKLEARN_RANDOM = {"train_test_split", "RandomForestClassifier", "RandomForestRegressor", "KMeans", "TSNE",
                  "UMAP", "ShuffleSplit", "StratifiedShuffleSplit", "GradientBoostingClassifier",
                  "GradientBoostingRegressor", "MLPClassifier", "MLPRegressor", "ExtraTreesClassifier",
                  "ExtraTreesRegressor", "MiniBatchKMeans", "GaussianMixture", "PCA_randomized",
                  "SGDClassifier", "SGDRegressor", "XGBClassifier", "XGBRegressor", "LGBMClassifier",
                  "LGBMRegressor", "RandomizedSearchCV", "IsolationForest", "BaggingClassifier"}
SEED_CALLS = {"seed", "manual_seed", "manual_seed_all", "set_seed", "seed_everything", "set_random_seed",
              "PRNGKey", "set_global_seed", "fix_seed", "set_seeds", "seed_all"}
SEEDED_CTORS = {"default_rng", "RandomState", "Generator", "Random", "SeedSequence"}


@dataclass
class Ref:
    path: str
    cell: Optional[int]
    line: int


@dataclass
class UnitFacts:
    unit: CodeUnit
    imports: List[Ref] = field(default_factory=list)  # path holds the top-level module name
    abs_paths: List[Ref] = field(default_factory=list)
    reads: List[Ref] = field(default_factory=list)
    writes: List[Ref] = field(default_factory=list)
    unresolved_writes: int = 0
    random_uses: List[Ref] = field(default_factory=list)
    has_seed: bool = False
    syntax_errors: List[Ref] = field(default_factory=list)
    # notebook name flow: per-cell (index, defs, [(name, line)], star)
    cell_flow: List[Tuple[int, Set[str], List[Tuple[str, int]], bool]] = field(default_factory=list)
    is_entrypoint: bool = False


# ---------------------------------------------------------------- python

_MAGIC_OK = {"%%time", "%%timeit", "%%capture", "%%prun"}


HELP_LINE = re.compile(r"^\?{1,2}[\w.]+$|^[\w.\[\]()]+\?{1,2}$")  # `obj?`, `obj??`, `?obj`
REGEX_DEFS = [
    re.compile(r"^\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*(?::[^=]+)?=(?!=)", re.M),
    re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"^\s*for\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s+in\b", re.M),
    re.compile(r"\bas\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*import\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"^\s*from\s+\S+\s+import\s+\(?([\w\s,]+)\)?\s*$", re.M),
]


def regex_defs(src: str) -> Set[str]:
    """Names a cell defines, for cells the running Python cannot parse (e.g. 3.12 f-strings on 3.9)."""
    out: Set[str] = set()
    for rx in REGEX_DEFS:
        for m in rx.finditer(src):
            out.update(n.strip() for n in m.group(1).split(",") if n.strip().isidentifier())
    return out


def clean_cell_source(src: str) -> Optional[str]:
    """Turn IPython cell source into parseable Python, keeping line numbers. None = not Python."""
    lines = src.splitlines()
    if lines and lines[0].startswith("%%"):
        if lines[0].split()[0] not in _MAGIC_OK:
            return None
        lines[0] = ""
    out = []
    for ln in lines:
        s = ln.lstrip()
        code = re.sub(r"\s+#.*$", "", s)  # a `?` inside a trailing comment is not IPython help
        if s.startswith(("%", "!")) or HELP_LINE.match(code):
            indent = ln[: len(ln) - len(s)]
            out.append(indent + "pass")
        else:
            out.append(ln)
    return "\n".join(out)


class _Resolver:
    """Resolve simple string expressions: literals, NAME = literal, os.path.join, Path / 'x', f-strings."""

    def __init__(self) -> None:
        self.names: Dict[str, str] = {}

    def resolve(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(str(v.value))
                elif isinstance(v, ast.FormattedValue):
                    r = self.resolve(v.value)
                    if r is None:
                        return None
                    parts.append(r)
            return "".join(parts)
        if isinstance(node, ast.BinOp):
            left, right = self.resolve(node.left), self.resolve(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Div):
                return posixpath.join(left, right)
            return None
        if isinstance(node, ast.Call):
            fn = _call_name(node)
            if fn in ("join",) and node.args:
                parts = [self.resolve(a) for a in node.args]
                if all(p is not None for p in parts):
                    return posixpath.join(*parts)  # type: ignore[arg-type]
            if fn in ("Path", "PurePath", "PosixPath", "abspath", "expanduser", "normpath", "str") and len(node.args) == 1:
                return self.resolve(node.args[0])
            if fn in ("Path",) and len(node.args) > 1:
                parts = [self.resolve(a) for a in node.args]
                if all(p is not None for p in parts):
                    return posixpath.join(*parts)  # type: ignore[arg-type]
            if fn == "format":
                return None
        return None


def _call_name(node: ast.Call) -> Optional[str]:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _call_chain(node: ast.Call) -> str:
    parts = []
    f = node.func
    while isinstance(f, ast.Attribute):
        parts.append(f.attr)
        f = f.value
    if isinstance(f, ast.Name):
        parts.append(f.id)
    return ".".join(reversed(parts))


def _looks_like_file(p: str) -> bool:
    if not p or "://" in p or len(p) > 300 or "\n" in p:
        return False
    if p.startswith(("http", "s3:", "gs:")):
        return False
    return bool(FILE_EXT.search(p.rstrip("/"))) or "/" in p


def _open_mode(node: ast.Call) -> str:
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        return node.args[1].value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return "r"


class _Flow(ast.NodeVisitor):
    """Collect names defined and names used at module scope of one cell."""

    def __init__(self) -> None:
        self.defs: Set[str] = set()
        self.uses: List[Tuple[str, int]] = []
        self.star = False

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.uses.append((node.id, node.lineno))
        else:
            self.defs.add(node.id)

    def _func(self, node) -> None:
        self.defs.add(node.name)
        for d in node.decorator_list:
            self.visit(d)
        for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x is not None]:
            self.visit(d)
        for sub in ast.walk(node):
            if isinstance(sub, (ast.Global, ast.Nonlocal)):
                self.defs.update(sub.names)

    visit_FunctionDef = _func
    visit_AsyncFunctionDef = _func

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults:
            self.visit(d)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defs.add(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            self.defs.add(a.asname or a.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for a in node.names:
            if a.name == "*":
                self.star = True
            else:
                self.defs.add(a.asname or a.name)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.defs.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in ("exec", "eval", "globals", "locals", "vars"):
            self.star = True
        self.generic_visit(node)


def analyze_python(unit: CodeUnit) -> UnitFacts:
    facts = UnitFacts(unit)
    resolver = _Resolver()
    for cell in unit.cells:
        if cell.kind != "code":
            continue
        src = clean_cell_source(cell.source) if unit.is_notebook else cell.source
        if src is None:
            continue
        _shell_downloads(cell, facts)
        if unit.is_notebook and re.search(r"^\s*%(run|store\s+-r|load)\b", cell.source, re.M):
            facts.cell_flow.append((cell.index or 0, set(), [], True))
        try:
            tree = ast.parse(src)
        except (SyntaxError, ValueError):
            facts.syntax_errors.append(Ref("", cell.index, 1))
            if unit.is_notebook:  # still record what it defines, so later cells are not misjudged
                facts.cell_flow.append((cell.index or 0, regex_defs(src), [], False))
            continue
        _scan_tree(tree, cell, facts, resolver)
        if unit.is_notebook:
            fl = _Flow()
            for stmt in tree.body:
                fl.visit(stmt)
            facts.cell_flow.append((cell.index or 0, fl.defs, fl.uses, fl.star))
    if not unit.is_notebook:
        facts.is_entrypoint = _is_script(unit.cells[0].source, facts)
    else:
        facts.is_entrypoint = True
    return facts


SHELL_DL = re.compile(r"^\s*!\s*(wget|curl)\b(.*)$", re.M)


def _shell_downloads(cell: Cell, facts: UnitFacts) -> None:
    """`!wget URL [-O out]` / `!curl -o out URL` in notebook cells create files."""
    for m in SHELL_DL.finditer(cell.source):
        args = m.group(2).split()
        out = None
        for i, a in enumerate(args):
            if a in ("-O", "-o", "--output", "--output-document") and i + 1 < len(args):
                out = args[i + 1]
            elif a.startswith("--output-document="):
                out = a.split("=", 1)[1]
            elif a.startswith("-P") and m.group(1) == "wget":
                pass
        if out is None:
            urls = [a for a in args if "://" in a]
            if urls:
                out = posixpath.basename(urls[0].strip("'\"").split("?")[0])
        if out:
            line = cell.source.count("\n", 0, m.start()) + 1
            facts.writes.append(Ref(out.strip("'\""), cell.index, line))


def _is_script(src: str, facts: UnitFacts) -> bool:
    if re.search(r"""if\s+__name__\s*==\s*['"]__main__['"]""", src):
        return True
    return bool(facts.reads or facts.writes)


def _scan_tree(tree: ast.AST, cell: Cell, facts: UnitFacts, resolver: _Resolver) -> None:
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 1)
        if isinstance(node, ast.Import):
            for a in node.names:
                facts.imports.append(Ref(a.name.split(".")[0], cell.index, line))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                facts.imports.append(Ref(node.module.split(".")[0], cell.index, line))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            val = resolver.resolve(node.value)
            if val is not None:
                resolver.names[node.targets[0].id] = val
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if ABS_PATH.match(v) and "\n" not in v and len(v) < 300 and " " not in v.strip()[:3]:
                facts.abs_paths.append(Ref(v, cell.index, line))
        elif isinstance(node, ast.Call):
            _scan_call(node, cell, facts, resolver, line)


def _first_path_arg(node: ast.Call, resolver: _Resolver, positions=(0,)) -> Optional[str]:
    for i in positions:
        if len(node.args) > i:
            v = resolver.resolve(node.args[i])
            if v is not None:
                return v
    for kw in node.keywords:
        if kw.arg in PATH_KWS:
            v = resolver.resolve(kw.value)
            if v is not None:
                return v
    return None


OUTPUT_DIR_KW = re.compile(r"^(output|out|save|results?|export)_?(dir|directory|folder|path)$|^outdir$", re.I)


def _scan_call(node: ast.Call, cell: Cell, facts: UnitFacts, resolver: _Resolver, line: int) -> None:
    name = _call_name(node)
    chain = _call_chain(node)
    if not name:
        return
    root = chain.split(".")[0] if chain else ""

    # ---- a tool told to write into a folder produces whatever is later read from it
    for kw in node.keywords:
        if kw.arg and OUTPUT_DIR_KW.match(kw.arg):
            d = resolver.resolve(kw.value)
            if d:
                facts.writes.append(Ref(d.rstrip("/") + "/*", cell.index, line))

    # ---- randomness
    if name in SEED_CALLS:
        facts.has_seed = True
    elif name in SEEDED_CTORS and (node.args or node.keywords):
        facts.has_seed = True
    elif name in SEEDED_CTORS:
        facts.random_uses.append(Ref(chain, cell.index, line))
    elif ".random." in f".{chain}." and name in RANDOM_NP and root in ("np", "numpy"):
        facts.random_uses.append(Ref(chain, cell.index, line))
    elif root == "random" and chain.count(".") == 1 and name in RANDOM_STDLIB:
        facts.random_uses.append(Ref(chain, cell.index, line))
    elif root == "torch" and name in RANDOM_TORCH:
        facts.random_uses.append(Ref(chain, cell.index, line))
    elif name in SKLEARN_RANDOM:
        if not any(kw.arg in ("random_state", "seed") for kw in node.keywords):
            facts.random_uses.append(Ref(chain, cell.index, line))
    if any(kw.arg == "random_state" for kw in node.keywords):
        facts.has_seed = True

    # ---- downloads produce files
    if name in ("download", "urlretrieve", "download_url", "download_file", "hf_hub_download"):
        target = _first_path_arg(node, resolver, (1,)) if name == "urlretrieve" else None
        for kw in node.keywords:
            if kw.arg in ("out", "filename", "fname", "path", "local_filename", "dest"):
                target = resolver.resolve(kw.value) or target
        url = _first_path_arg(node, resolver, (0,))
        if target is None and url and "://" in url:
            target = posixpath.basename(url.split("?")[0])
        if target:
            facts.writes.append(Ref(target, cell.index, line))
        return

    # ---- file reads
    if name == "open" or (name == "File" and root in ("h5py", "File")):
        if root not in ("", "open", "io", "h5py", "File", "codecs", "gzip", "bz2"):
            return
        path = _first_path_arg(node, resolver)
        mode = _open_mode(node)
        if path is None:
            if any(c in mode for c in "wax"):
                facts.unresolved_writes += 1
            return
        target = facts.writes if any(c in mode for c in "wax") else facts.reads
        target.append(Ref(path, cell.index, line))
        return
    if name in ("read_text", "read_bytes") and node.args:
        return  # Path.read_text() takes no path; with an argument it is importlib.metadata/resources
    if name in READERS and name not in ("open", "File"):
        if name == "load" and root not in ("np", "numpy", "torch", "joblib", "nib", "nibabel", "sio", "scipy",
                                            "librosa", "mne", "json", "pickle", "yaml", "dill", "h5py", "loadmat"):
            return
        path = _first_path_arg(node, resolver)
        if path is not None and _looks_like_file(path):
            facts.reads.append(Ref(path, cell.index, line))
        return
    if name in WRITERS:
        positions = (1, 0) if name in ("save", "dump") and root in ("torch", "joblib", "pickle") else (0, 1)
        path = _first_path_arg(node, resolver, positions)
        if path is not None and _looks_like_file(path):
            facts.writes.append(Ref(path, cell.index, line))
        elif name in ("savefig", "to_csv", "save", "imwrite", "imsave", "savetxt", "to_parquet", "to_pickle",
                      "write_h5ad", "to_netcdf", "write_image"):
            facts.unresolved_writes += 1


# ---------------------------------------------------------------- R (regex based)

R_STR = re.compile(r"""(["'])((?:(?!\1)[^\\\n]|\\.)*)\1""")


def analyze_r(unit: CodeUnit) -> UnitFacts:
    facts = UnitFacts(unit, is_entrypoint=True)
    for cell in unit.cells:
        if cell.kind != "code":
            continue
        for n, raw in enumerate(cell.source.splitlines(), 1):
            line = raw.split("#")[0] if "#" in raw and not re.search(r"[\"'][^\"']*#", raw) else raw
            for m in re.finditer(r"\b(?:library|require)\(\s*[\"']?([A-Za-z0-9.]+)|"
                                 r"\brequireNamespace\(\s*[\"']([A-Za-z0-9.]+)[\"']", line):
                facts.imports.append(Ref(m.group(1) or m.group(2), cell.index, n))
            for m in re.finditer(r"\b(?:p_load)\(([^)]*)\)", line):
                for pkg in re.findall(r"[A-Za-z][A-Za-z0-9.]+", m.group(1)):
                    facts.imports.append(Ref(pkg, cell.index, n))
            for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9.]+)::", line):
                facts.imports.append(Ref(m.group(1), cell.index, n))
            for m in R_STR.finditer(line):
                if ABS_PATH.match(m.group(2)):
                    facts.abs_paths.append(Ref(m.group(2), cell.index, n))
            for m in re.finditer(r"\b" + R_READERS + r"\(\s*(?:file\s*=\s*)?([\"'])([^\"']+)\1", line):
                if _looks_like_file(m.group(2)):
                    facts.reads.append(Ref(m.group(2), cell.index, n))
            for m in re.finditer(r"\b" + R_WRITERS + r"\(([^)]*)", line):
                for s in R_STR.finditer(m.group(1)):
                    if _looks_like_file(s.group(2)):
                        facts.writes.append(Ref(s.group(2), cell.index, n))
                        break
            if re.search(r"\bset\.seed\(", line):
                facts.has_seed = True
            rm = re.search(r"\b(sample|rnorm|runif|rbinom|rpois|sample_n|sample_frac|slice_sample|kmeans|randomForest|createDataPartition|rexp|rgamma|rbeta)\(", line)
            if rm:
                facts.random_uses.append(Ref(rm.group(1), cell.index, n))
    return facts


def analyze_unit(unit: CodeUnit) -> UnitFacts:
    return analyze_r(unit) if unit.lang == "r" else analyze_python(unit)


def norm_rel(base_dir: str, p: str) -> str:
    """Normalize p (relative to base_dir) into a repo-relative posix path."""
    p = p.replace("\\", "/")
    joined = posixpath.normpath(posixpath.join(base_dir, p)) if base_dir else posixpath.normpath(p)
    return joined
