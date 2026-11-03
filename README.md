# Reproducibility Debt Scanner

Point it at a research code repository (Python scripts, Jupyter notebooks, R) and get **one scored,
prioritized report** of everything likely to stop someone else from re-running it: missing or unpinned
dependencies, hardcoded paths, missing input files, notebooks run out of order, unseeded randomness,
undocumented pipeline steps, missing README/license/data note.

It is written for the people who have to judge or fix reproducibility without reading every line:
journal reproducibility editors, research software engineers and data stewards. The output is plain
English and ends with a **top 5 fixes** list a researcher can act on in an afternoon.

- Static analysis only. It never runs or imports your code, so it is safe on untrusted repos and takes
  under a second on typical paper repos.
- No dependencies. Pure Python 3.9+ standard library.
- Markdown for humans, JSON for tools, GitHub annotations for CI.

How it differs from existing tools: ReproZip and repo2docker/Binder *capture or rebuild* an environment;
linters flag style. This tool *diagnoses* the repo as it stands and ranks the debt, so you know what to fix
first and whether a step is runnable at all.

## Install

```bash
pip install git+https://github.com/Yenula-W/repro-debt-scanner   # or, from a checkout:
pip install .
```

## Usage

```bash
repro-debt scan path/to/repo                       # Markdown report to stdout
repro-debt scan path/to/repo --md report.md --json report.json -q
repro-debt scan . --fail-above 25                  # exit 1 if debt score > 25 (for CI)
repro-debt scan . --github-annotations             # ::error file=...:: lines for GitHub Actions
repro-debt scan . --exclude tests --exclude 'vendor/*'   # skip paths
repro-debt scan . --all-checks                     # include the opt-in checks
repro-debt checks                                  # list all checks ([opt-in] marked)
```

`python -m repro_debt scan ...` works too.

## What it checks

| ID | Severity | What it finds |
|---|---|---|
| DEP001 | high | No requirements.txt / environment.yml / pyproject / setup.py / Pipfile / DESCRIPTION / renv.lock / Dockerfile |
| DEP002 | medium | Dependencies without exact versions (skipped when a lock file exists) |
| DEP003 | medium | Packages imported in code but not declared (knows `sklearn`→`scikit-learn`, `cv2`→`opencv-python`, …; ignores stdlib and local modules) |
| ENV001 | medium | Python/R version not recorded (`.python-version`, `requires-python`, `python=` in environment.yml, `FROM python:3.x`, …) |
| PATH001 | high | **Opt-in.** Absolute paths like `/Users/…`, `/home/…`, `C:\…`, `/scratch/…` |
| DATA001 | high | **Opt-in.** Files the code reads that are not in the repo and that nothing in the repo creates or downloads |
| WF001 | medium | **Opt-in.** Undocumented intermediate step: script B reads a file only script A writes, and no Makefile/Snakefile/run_all/README says to run A first |
| RAND001 | medium | Randomness (`np.random`, `random`, `torch.rand*`, scikit-learn without `random_state`, R `sample()`/`rnorm()`…) with no seed |
| NB001 | medium | Notebook cells executed out of order (execution counts go backwards) |
| NB002 | high | Notebook cell uses a name that is only defined in a *later* cell (hidden kernel state) |
| NB003 | medium | Notebook uses a name never defined or imported |
| NB004 | low | Saved outputs not from a clean run (counts don't start at 1, gaps, unrun cells) |
| NB005 | medium | Notebook saved showing an error, classified as data / dependency / code |
| FIG001 | low | **Opt-in.** Figures in `figures/`, `results/`, … that no code writes |
| DOC001–003 | high/medium | No README; README without run commands; no LICENSE |
| DOC004 | medium | **Opt-in.** Code reads data but the README has no data-availability note |

**On by default vs opt-in.** The opt-in checks (PATH001, DATA001, WF001, FIG001, DOC004) missed the precision
bar (at least 90% overall and no check below 80%) on the last held-out round in [EVALUATION.md](EVALUATION.md), so they are off unless
you pass `--all-checks` (or `--enable PATH001`, etc.). Their findings are often right but need a human
to skim them first. With them off, the step table only shows dependency and notebook blockers.

File paths are resolved through simple constants (`DATA = "data"`, `Path(DATA) / "x.csv"`,
`os.path.join`, f-strings). Downloads (`!wget`, `!curl -o`, `urlretrieve`, `wget.download`) count as
producing the file. A relative path that matches the tail of any file in the repo counts as present
(code often runs from another working directory), which trades a few missed issues for far fewer false alarms.

### Partial reproducibility and failure diagnosis

Every script and notebook is listed as a **step** with a status:

- ✅ **runnable**: no blockers detected
- ⏳ **needs earlier step**: its inputs are produced by another script (listed)
- ❌ **blocked**: with the *likely cause if it breaks*: `data` (missing input, absolute path),
  `dependency` (undeclared package, no dependency file) or `code` (hidden notebook state, saved errors,
  unparseable cells). Saved notebook errors are classified from the exception
  (`ModuleNotFoundError` → dependency, `FileNotFoundError` → data, otherwise code).

## Score

Each issue type adds points by severity: high 10, medium 4, low 1, counted at most 3 times per type so one
noisy problem cannot dominate. Lower is better.

| Debt | Grade | Meaning |
|---|---|---|
| 0 | A | No debt found |
| 1–10 | B | A stranger could probably re-run this with a little effort |
| 11–25 | C | Expect hours of work |
| 26–50 | D | Likely needs the authors' help |
| > 50 | F | Very unlikely to reproduce as-is |

Top fixes are the issue types contributing the most points, each with a concrete instruction and examples.

## Example report

From [`examples/messy-lab-repo`](examples/messy-lab-repo), scanned with `--all-checks` (full output in
[`examples/messy-lab-repo-report.md`](examples/messy-lab-repo-report.md)):

> **Debt score: 75 points — grade F.**
>
> ## Top fixes
> 1. **Input file missing and nothing creates it** (high, 1 found, 10 pts) — Include these input files, or explain in the README where to download them and where to put them: `data/plate_metadata.csv`.
> 2. **Notebook uses a name defined in a later cell** (high, 1 found, 10 pts) — Move the cell that defines these names above the cell that uses them, then Restart & Run All: `figures.ipynb:rates`.
> 3. **Hardcoded absolute path** (high, 1 found, 10 pts) — Replace absolute paths that only exist on your computer with paths relative to the repository (e.g. `Path(__file__).parent / 'data'`). Found: `/Users/alice/Dropbox/lab/raw_counts.csv`.
> 4. **Imported package not declared** (medium, 2 found, 8 pts) — Add the packages your code imports but your dependency file does not list: `matplotlib`, `sklearn`.
> 5. **Dependencies without exact versions** (medium, 1 found, 4 pts) — Pin exact versions (e.g. `numpy==1.26.4`) so others install what you used. Unpinned: `requirements.txt`.
>
> ## Can each step be re-run?
> | Step | Status | Likely cause if it breaks | Why |
> |---|---|---|---|
> | `figures.ipynb` | ❌ blocked | data | undeclared package `matplotlib`; hidden-state name `rates`; saved error `FileNotFoundError: clean_counts.csv`; needs output of `scripts/01_clean.py` |
> | `scripts/01_clean.py` | ❌ blocked | data | absolute path `/Users/alice/Dropbox/lab/raw_counts.csv` |
> | `scripts/02_fit.py` | ❌ blocked | data | undeclared package `sklearn`; missing input `data/plate_metadata.csv`; needs output of `scripts/01_clean.py` |

### Tested on real public repositories

| Repository | Kind | Debt / grade | Runnable steps |
|---|---|---|---|
| [benmarwick/1989-excavation-report-Madjebebe](https://github.com/benmarwick/1989-excavation-report-Madjebebe) | R research compendium | 5 / B | 3 of 3 |
| [pachterlab/BYVSTZP_2020](https://github.com/pachterlab/BYVSTZP_2020) | Paper notebooks (single-cell) | 113 / F | 0 of 55 |
| [theislab/scgen-reproducibility](https://github.com/theislab/scgen-reproducibility) | Paper notebooks | 87 / F | 1 of 35 |
| [CamDavidsonPilon/Probabilistic-Programming-and-Bayesian-Methods-for-Hackers](https://github.com/CamDavidsonPilon/Probabilistic-Programming-and-Bayesian-Methods-for-Hackers) | Notebook book | 77 / F | 26 of 38 |

Each scan took under a second. Grades for large notebook collections are dominated by external data
(expected for single-cell work) and notebook execution order; the R compendium, built with
reproducibility in mind, scores well.

## GitHub Action

```yaml
name: Reproducibility
on: [pull_request, push]
permissions:
  contents: read
  pull-requests: write   # only needed for the PR comment
jobs:
  repro-debt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Yenula-W/repro-debt-scanner@main
        with:
          path: .            # directory to scan
          exclude: ""        # e.g. "tests vendor/*"
          all-checks: "false"  # "true" adds the opt-in checks
          fail-above: ""     # e.g. "25" to fail the job above that score
          comment: "true"    # post/update a summary comment on PRs
```

The action installs the scanner, writes the full report to the job summary, annotates files with findings,
posts the top fixes and step table as a PR comment, and exposes `score`, `grade`, `report-md` and
`report-json` outputs. While this repository is private, the action can only be used from repositories
the same account owns, with Actions access enabled in the repo settings.

## Limits (MVP)

- Static only: it cannot know what a dynamically built path points to, or whether code actually runs.
- Undeclared-import detection uses a name mapping, not package metadata, so unusual import names may be missed.
- R support is regex based (`library()`, `pkg::`, `read.csv()`, `set.seed()`…); Python is AST based.
- Quarto/`.qmd`, Julia, MATLAB, Snakemake rule parsing and container builds are not covered yet.

## Development

```bash
pip install -e ".[test]"
pytest
```

`.github/workflows/ci.yml` runs the tests on Python 3.9 and 3.12 and self-tests the Action.
