"""Core data types and the check registry."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

SEVERITY_WEIGHT = {"high": 10, "medium": 4, "low": 1}
# A single check type can't dominate the score: repeated findings of the same
# kind count at most this many times.
PER_CHECK_CAP = 3


@dataclass
class CheckInfo:
    id: str
    title: str
    severity: str
    category: str  # dependency | data | code | environment | docs | workflow
    fix: str  # plain-English fix; may contain {examples}


CHECKS: Dict[str, CheckInfo] = {
    c.id: c
    for c in [
        CheckInfo("DEP001", "No dependency file", "high", "dependency",
                  "Add a requirements.txt (or environment.yml) listing every package the code needs. "
                  "From your working environment run `pip freeze > requirements.txt` and trim it to what you import."),
        CheckInfo("DEP002", "Dependencies without exact versions", "medium", "dependency",
                  "Pin exact versions (e.g. `numpy==1.26.4`) so others install what you used. "
                  "Unpinned: {examples}."),
        CheckInfo("DEP003", "Imported package not declared", "medium", "dependency",
                  "Add the packages your code imports but your dependency file does not list: {examples}."),
        CheckInfo("ENV001", "Python/R version not recorded", "medium", "environment",
                  "Record the language version you used, e.g. `python=3.11` in environment.yml, "
                  "`requires-python` in pyproject.toml, or a `.python-version` file."),
        CheckInfo("PATH001", "Hardcoded absolute path", "high", "data",
                  "Replace absolute paths that only exist on your computer with paths relative to the repository "
                  "(e.g. `Path(__file__).parent / 'data'`). Found: {examples}."),
        CheckInfo("DATA001", "Input file missing and nothing creates it", "high", "data",
                  "Include these input files, or explain in the README where to download them and where to put them: "
                  "{examples}."),
        CheckInfo("WF001", "Undocumented intermediate step", "medium", "workflow",
                  "Document the order the scripts must run in (a numbered list in the README, a run_all.sh, "
                  "or a Makefile/Snakefile). Unclear: {examples}."),
        CheckInfo("RAND001", "Randomness without a fixed seed", "medium", "code",
                  "Set a random seed at the top of each script/notebook that uses randomness "
                  "(`np.random.seed(0)`, `random.seed(0)`, `torch.manual_seed(0)`, `set.seed(0)` in R) "
                  "and pass `random_state=` to scikit-learn. Affected: {examples}."),
        CheckInfo("NB001", "Notebook cells executed out of order", "medium", "code",
                  "Restart the kernel and run each notebook top-to-bottom (Kernel > Restart & Run All), then save. "
                  "Affected: {examples}."),
        CheckInfo("NB002", "Notebook uses a name defined in a later cell", "high", "code",
                  "Move the cell that defines these names above the cell that uses them, then Restart & Run All: "
                  "{examples}."),
        CheckInfo("NB003", "Notebook uses a name that is never defined", "medium", "code",
                  "These names are used but never created in the notebook (likely leftover kernel state). "
                  "Define or import them: {examples}."),
        CheckInfo("NB004", "Saved notebook outputs may not be regenerable", "low", "code",
                  "Outputs were saved from a partial or non-linear session. Restart & Run All before committing: "
                  "{examples}."),
        CheckInfo("NB005", "Notebook saved with error outputs", "medium", "code",
                  "These notebooks were saved showing errors; fix them and re-run: {examples}."),
        CheckInfo("FIG001", "Result figures with no code that produces them", "low", "workflow",
                  "Add or point to the code that generates these figures (or note they were made by hand): "
                  "{examples}."),
        CheckInfo("DOC001", "No README", "high", "docs",
                  "Add a README.md explaining what the code does, how to install dependencies and how to run it."),
        CheckInfo("DOC002", "README lacks run instructions", "medium", "docs",
                  "Add a 'How to reproduce' section to the README with the exact commands, in order, "
                  "that regenerate your results."),
        CheckInfo("DOC003", "No license", "medium", "docs",
                  "Add a LICENSE file (MIT or BSD-3 are common for research code) so others are allowed to reuse it."),
        CheckInfo("DOC004", "No data availability note", "medium", "docs",
                  "The code reads data files. Add a 'Data availability' section to the README saying where the data "
                  "lives (e.g. a Zenodo/Figshare DOI) and how to obtain it."),
    ]
}


@dataclass
class Finding:
    check: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    cell: Optional[int] = None
    detail: Optional[str] = None  # short token used in "top fixes" examples
    severity: str = ""
    category: str = ""

    def __post_init__(self) -> None:
        info = CHECKS[self.check]
        self.severity = self.severity or info.severity
        self.category = self.category or info.category

    @property
    def location(self) -> str:
        if not self.file:
            return "(repository)"
        loc = self.file
        if self.cell is not None:
            loc += f" cell {self.cell}"
            if self.line is not None:
                loc += f" line {self.line}"
        elif self.line is not None:
            loc += f":{self.line}"
        return loc

    def to_dict(self) -> dict:
        d = asdict(self)
        d["title"] = CHECKS[self.check].title
        d["location"] = self.location
        return d


@dataclass
class Step:
    """A runnable unit (script or notebook) and whether it can be re-run."""
    file: str
    status: str = "runnable"  # runnable | blocked | needs-upstream
    likely_break: Optional[str] = None  # data | dependency | code | None
    reasons: List[str] = field(default_factory=list)
    upstream: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
