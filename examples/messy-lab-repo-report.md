# Reproducibility debt report: `messy-lab-repo`

**Debt score: 46 points — grade D.** Heavy debt; re-running this would likely need help from the authors.

1 high, 9 medium, 0 low severity issues (+5 that need review, not counted) · 2 Python files, 1 notebooks, 0 R files · dependency files: requirements.txt

_Lower is better. Each issue type adds points by severity (high 10, medium 4, low 1), counted at most 3 times._

## Top fixes

1. **Notebook uses a name defined in a later cell** (high, 1 found, 10 pts) — Move the cell that defines these names above the cell that uses them, then Restart & Run All: `figures.ipynb:rates`.
2. **Imported package not declared** (medium, 2 found, 8 pts) — Add the packages your code imports but your dependency file does not list: `matplotlib`, `sklearn`.
3. **Dependencies without exact versions** (medium, 1 found, 4 pts) — Pin exact versions (e.g. `numpy==1.26.4`) so others install what you used. Unpinned: `requirements.txt`.
4. **README lacks run instructions** (medium, 1 found, 4 pts) — Add a 'How to reproduce' section to the README with the exact commands, in order, that regenerate your results.
5. **No license** (medium, 1 found, 4 pts) — Add a LICENSE file (MIT or BSD-3 are common for research code) so others are allowed to reuse it.

## Can each step be re-run?

0 of 3 scripts/notebooks have no detected blockers.

| Step | Status | Likely cause if it breaks | Why |
|---|---|---|---|
| `figures.ipynb` | ❌ blocked | data | undeclared package `matplotlib`; hidden-state name `rates`; saved error `FileNotFoundError: clean_counts.csv`; needs output of `scripts/01_clean.py` (needs review) |
| `scripts/01_clean.py` | ❌ blocked | data | absolute path `/Users/alice/Dropbox/lab/raw_counts.csv` (needs review) |
| `scripts/02_fit.py` | ❌ blocked | data | undeclared package `sklearn`; missing input `data/plate_metadata.csv` (needs review); needs output of `scripts/01_clean.py` (needs review) |

## All findings

| Severity | Check | Where | What |
|---|---|---|---|
| high | NB002 Notebook uses a name defined in a later cell | `figures.ipynb cell 1 line 2` | Cell 1 uses `rates`, which is only defined later in cell 2; this only worked because of hidden kernel state. |
| medium | DEP002 Dependencies without exact versions | `requirements.txt:1` | 2 of 2 packages in requirements.txt have no exact version: pandas, numpy. |
| medium | DEP003 Imported package not declared | `figures.ipynb cell 1 line 1` | `matplotlib` is imported but not listed in any dependency file (requirements.txt). |
| medium | DEP003 Imported package not declared | `scripts/02_fit.py:3` | `sklearn` is imported but not listed in any dependency file (requirements.txt). |
| medium | DOC002 README lacks run instructions | `README.md` | The README does not show any commands for installing or running the code. |
| medium | DOC003 No license | `(repository)` | No LICENSE file found; by default nobody may legally reuse this code. |
| medium | ENV001 Python/R version not recorded | `(repository)` | The Python version used is not recorded anywhere (notebook metadata says 3.9.7, but that is not an installable spec). |
| medium | NB001 Notebook cells executed out of order | `figures.ipynb cell 2` | Cell 2 (run #3) was executed before cell 1 (run #7) above it; the saved results came from running cells out of order. |
| medium | NB005 Notebook saved with error outputs | `figures.ipynb cell 3` | Cell 3 was saved showing `FileNotFoundError: clean_counts.csv` (looks like a data problem). |
| medium | RAND001 Randomness without a fixed seed | `scripts/02_fit.py:7` | Uses randomness (np.random.normal, train_test_split; 2 call(s)) without setting a seed, so results can differ between runs. |

## Needs review (5)

_These come from less reliable checks: in held-out tests about half of them were wrong (see EVALUATION.md). Check each one against the code before acting. They do not count toward the grade._

| Severity | Check | Where | What |
|---|---|---|---|
| high · ⚠️ needs review | DATA001 Input file missing and nothing creates it | `scripts/02_fit.py:6` | Reads `data/plate_metadata.csv`, which is not in the repository and no script creates it. |
| high · ⚠️ needs review | PATH001 Hardcoded absolute path | `scripts/01_clean.py:3` | Absolute path `/Users/alice/Dropbox/lab/raw_counts.csv` only exists on the author's machine. |
| medium · ⚠️ needs review | DOC004 No data availability note | `README.md` | The code reads data files but the README does not say where the data comes from or how to get it. |
| medium · ⚠️ needs review | WF001 Undocumented intermediate step | `figures.ipynb cell 2 line 2` | Reads `clean_counts.csv`, which is created by `scripts/01_clean.py`, but nothing says `scripts/01_clean.py` must run first. |
| low · ⚠️ needs review | FIG001 Result figures with no code that produces them | `figures/fig2_supplement.png` | 1 figure/result file(s) have no code in the repo that writes them: figures/fig2_supplement.png. |

<sub>Generated by repro-debt-scanner 0.1.0. Static analysis only: it does not run your code, so treat findings as leads, not verdicts.</sub>
