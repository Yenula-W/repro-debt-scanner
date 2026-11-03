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
repro-debt scan . --confident-only                 # hide findings marked "needs review"
repro-debt checks                                  # list checks, measured precision, [needs review] tags
```

`python -m repro_debt scan ...` works too.

## What it checks

| ID | Severity | Precision* | What it finds |
|---|---|---|---|
| DEP001 | high | 100% (14/14) | No requirements.txt / environment.yml / pyproject / setup.py / Pipfile / DESCRIPTION / renv.lock / Dockerfile |
| DEP002 | medium | 93% (14/15) | Dependencies without exact versions (skipped when a lock file exists) |
| DEP003 | medium | 67% (10/15) | Packages imported in code but not declared (knows `sklearn`→`scikit-learn`, `cv2`→`opencv-python`, …; ignores stdlib and local modules) |
| ENV001 | medium | 80% (12/15) | Python/R version not recorded (`.python-version`, `requires-python`, `python=` in environment.yml, `FROM python:3.x`, …) |
| PATH001 | high | 33% (5/15) | **Needs review.** Absolute paths like `/Users/…`, `/home/…`, `C:\…`, `/scratch/…` |
| DATA001 | high | 53% (8/15) | **Needs review.** Files the code reads that are not in the repo and that nothing in the repo creates or downloads |
| WF001 | medium | 67% (10/15) | **Needs review.** Undocumented intermediate step: script B reads a file only script A writes, and no Makefile/Snakefile/run_all/README says to run A first |
| RAND001 | medium | 87% (13/15) | Randomness (`np.random`, `random`, `torch.rand*`, scikit-learn without `random_state`, R `sample()`/`rnorm()`…) with no seed |
| NB001 | medium | 100% (15/15) | Notebook cells executed out of order (execution counts go backwards) |
| NB002 | high | 100% (7/7) | Notebook cell uses a name that is only defined in a *later* cell (hidden kernel state) |
| NB003 | medium | 83% (10/12) | Notebook uses a name never defined or imported |
| NB004 | low | 100% (15/15) | Saved outputs not from a clean run (counts don't start at 1, gaps, unrun cells) |
| NB005 | medium | 89% (8/9) | Notebook saved showing an error, classified as data / dependency / code |
| FIG001 | low | 50% (1/2) | **Needs review.** Figures in `figures/`, `results/`, … that no code writes |
| DOC001–003 | high/medium | n/a · 100% · 100% | No README; README without run commands; no LICENSE |
| DOC004 | medium | 25% (1/4) | **Needs review.** Code reads data but the README has no data-availability note |

\* Untouched, hand-checked precision on 75 held-out repos (correct + debatable / sampled), from the ship-bar rounds in [EVALUATION.md](EVALUATION.md) section 7. Fixes made after each round are not reflected.

**Confident vs "needs review".** Every check runs by default. Five of them (PATH001, DATA001, WF001,
FIG001 and DOC004) missed the precision bar in held-out tests. About half of their sampled findings were wrong,
before the fixes that followed. Their findings are tagged **needs review** everywhere:
- in a separate "Needs review" section after the confident findings in the Markdown/terminal report
- with `"needs_review": true` in the JSON
- as `notice` annotations titled `[needs review]` in GitHub Actions

They never count toward the debt score or grade, and never appear in the top fixes, so a doubtful finding cannot
lower a repo's grade. `--confident-only` hides them. Step-table reasons from these checks also say "(needs review)".

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

From [`examples/messy-lab-repo`](examples/messy-lab-repo) (full output in
[`examples/messy-lab-repo-report.md`](examples/messy-lab-repo-report.md)). The grade counts only the confident
findings; the five findings that need review are listed after them:

> **Debt score: 46 points — grade D.**
>
> ## Needs review> (5)
>
> _These come from less reliable checks: in held-out tests about half of them were wrong (see EVALUATION.md). Check each one against the code before acting. They do not count toward the grade._
>
> | Severity | Check | Where | What |
> |---|---|---|---|
> | high · ⚠️ needs review | DATA001 Input file missing and nothing creates it | `scripts/02_fit.py:6` | Reads `data/plate_metadata.csv`, which is not in the repository and no script creates it. |
> | high · ⚠️ needs review | PATH001 Hardcoded absolute path | `scripts/01_clean.py:3` | Absolute path `/Users/alice/Dropbox/lab/raw_counts.csv` only exists on the author's machine. |
> | medium · ⚠️ needs review | DOC004 No data availability note | `README.md` | The code reads data files but the README does not say where the data comes from or how to get it. |
> | medium · ⚠️ needs review | WF001 Undocumented intermediate step | `figures.ipynb cell 2 line 2` | Reads `clean_counts.csv`, which is created by `scripts/01_clean.py`, but nothing says `scripts/01_clean.py` must run first. |
> | low · ⚠️ needs review | FIG001 Result figures with no code that produces them | `figures/fig2_supplement.png` | 1 figure/result file(s) have no code in the repo that writes them: figures/fig2_supplement.png. |

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
          confident-only: "false"  # "true" hides findings marked "needs review"
          fail-above: ""     # e.g. "25" to fail the job above that score
          comment: "true"    # post/update a summary comment on PRs
```

The action installs the scanner, writes the full report to the job summary, annotates files with findings,
posts the top fixes and step table as a PR comment, and exposes `score`, `grade`, `report-md` and
`report-json` outputs.

## Limitations

- **Static analysis only.** It never runs your code, so it cannot see runtime failures, wrong results, or what a
  path built at runtime points to.
- **"Needs review" checks are often wrong.** PATH001, DATA001, WF001, FIG001 and DOC004 had about 50% untouched
  precision on held-out repos. Their findings are listed separately and never count toward the grade. Check each
  one before passing it on.
- **Confident checks are not perfect either.** Each round sampled only about 5 findings per check. DEP003 (undeclared
  imports) uses a name map, not package metadata, so unusual import names can be wrong; its pooled precision was
  67%. A person should skim any report before sending it to an author.
- **Local-module imports aren't checked.** It doesn't spot a notebook in a subfolder that imports a repo-root module
  without a `sys.path` change.
- **R support is regex based** (`library()`, `pkg::`, `read.csv()`, `set.seed()`…); Python is AST based.
- **Not covered yet:** Quarto/`.qmd`, Julia, MATLAB, Snakemake rule bodies and container builds.

See [EVALUATION.md](EVALUATION.md) for how it was measured.

## Development

```bash
pip install -e ".[test]"
pytest
```

`.github/workflows/ci.yml` runs the tests on Python 3.9 and 3.12 and self-tests the Action.
