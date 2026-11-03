# Evaluation

Measured on 2026-11-02/03 against the shared adoption-ready bar (`~/Desktop/LabAdoption/ADOPTION_BAR.md`).
Summary: **ready for a supervised pilot** (you run it and send reviewed reports). Known gaps are listed at the
end.

## 1. Robustness

`tests/test_robustness.py` (20 cases) covers:
- an empty repo, and a README-only repo
- binary, non-UTF8, empty and syntax-error `.py` files
- 7 kinds of malformed notebook: not JSON, a list, wrong types, `null` sources, odd outputs, nbformat 3
- magics and shell escapes in notebooks
- symlink loops and broken links
- corrupt zip/tar files
- a 3 MB source file
- R-only repos and R kernels
- unicode and deeply nested paths
- vendored directories that should be skipped

One crash was found and fixed: a notebook cell with `"source": null`.
On the real-world runs below there were **0 crashes across 70 repos**.

## 2. Install

`pip install git+https://github.com/Yenula-W/repro-debt-scanner` was tested in fresh virtual environments:

| Python | Install time | Result on `examples/messy-lab-repo` |
|---|---|---|
| 3.9 (macOS system Python, pip 21.2) | 10 s | OK, 16 findings |
| 3.12 | 3 s | OK, 16 findings, identical |
| 3.13 | 1 s | OK, 16 findings, identical |

CI on GitHub runs the tests on Python 3.9 and 3.12, plus a self-test of the Action. It is green.

## 3. Held-out real-world run

The scanner was run on **58 public research repos** that were not used during development. They were chosen by
GitHub topic: genomics 14, ecology 13, neuroscience 7, epidemiology 6, climate 6, psychology 5, hydrology 3, and
others. By main language: 24 Jupyter, 24 R and 10 Python.

Results: 0 crashes, at most 5.5 s per repo (most under 1 s), and 776 findings in the final run.

It was also run on the 12 repos used for outreach batch 1. Those were hand-checked separately; see
`~/Desktop/LabAdoption/outreach/repro-debt-batch1`.

Repos: GenoMAS, Physics-aware-Multiplex-GNN, snputils, xhydro, GENetLib, aquascope, GeoAnalyze, envoi, easymeta,
STEM-Automated-Nanoparticle-Analysis, SNPBag, hce-classification, pinn-infectious-disease,
generalized_contrastive_PCA, RiverMamba_code, Analysis-of-pollination-in-the-Pyrenees,
Psychological-Disorders-EEG-Data, TraitGym, GenoTEX, scFM-dataselection, alphagenome, neural-dynamics-gyration,
lotkavolterra_simulator, eye-tracking-ASD-Analysis, SEQTaRget, multiRL, brfssTools, Conservation_statistics,
RNA_QC_APP, SoilMicrobeDB, ddrp_v3, ggwas, climniche, binaryRL, ColOpenData, R-Plot-Code, coconatfly,
animovement, neurodatasets, Phage-plasmids, cleanepi, rcdo, F32_Details, biomed-multi-omic, findr, BlueCarbon,
naturelab, DeepCRE, ReMatch, scMulan, ukb_sleep_enhancement, CAMELE, intro-to-eeg, themissingsemester,
BioTIMEr, ggsurveillance, climate-emulator, readnoaa.

## 4. Precision, checked by hand

Each round took a fresh stratified random sample: about 5 findings per check across all 18 checks, then each
finding was read against the actual source line. Each finding was labelled one of:
- **correct**
- **wrong**: false
- **debatable**: true, but arguably not worth fixing

After each round, every wrong finding was fixed at the root and given a regression test before re-measuring.

| Round | Sample | Correct | Debatable | Wrong | What was fixed after the round |
|---|---|---|---|---|---|
| 1 | 85 | 59 (69%) | 9 | 17 | 9 kinds of false alarm: R `DESCRIPTION` pins, docs and dev requirement files, randomness in tests and library modules, `?` in comments read as IPython help, cells newer Python syntax can't parse, logos and package-doc images, interrupted cells, `importlib` `read_text`, conda files under `workflow/envs` |
| 2 | 85 | 72 (85%) | 7 | 6 | `pyproject`/`setup.py` ranges, `requireNamespace(var)`, `output_dir=` producing files, `~/folder`, images shown in the README |
| 3 | 85 | 75 (88%) | 6 | 4 | UTF-16 `requirements.txt` from PowerShell, `hydra`→`hydra-core` and other name maps, `Path(x).open("r+")`, marimo exports |
| 4 (high-volume checks only) | 49 | 41 (84%) | 7 | **1 (2%)** | `README.Rmd` install commands |

Final state: **2% of findings are wrong.** About 14% are true but debatable: unseeded randomness in throwaway
smoke tests, dev-only `data-raw/` and benchmark scripts, and packages Colab already has. All the other checks
(PATH001, NB001/2/4, WF001, DEP001/2, DOC00x, ENV001) had no wrong findings in rounds 3 and 4.

The wording of RAND001 was softened to "results can differ between runs", because most of its debatable cases
are true but low-stakes.

## 5. Does it catch problems real users hit?

For all 70 scanned repos, every GitHub issue was searched for reports of failing to run the code: module and
file-not-found errors. Two concrete reports turned up:

| Repo | Real user report | Flagged before? |
|---|---|---|
| NAMlab/DeepCRE | `FileNotFoundError: gene_models/zea_sol_ara_sor_52.gtf` (issue #1) | **Yes.** WF001 names that exact file and the script that creates it. |
| Liu-Hy/GenoTEX | `ModuleNotFoundError: No module named 'utils'` (issue #1) | **No.** The notebook in a subfolder imports a top-level repo module. This is not detected yet (see limitations). |

The sample is small (2 issues), so treat it as anecdotal. It does show that the scanner's findings line up with
real failures.

## 6. Messages

Every message names the file, the line or cell, and what to change. None of them calls a recommendation an
"error". Outreach copies of the reports leave out the debt grade.

## Known limitations

- **Static analysis only.** It never runs code, so problems that only appear at runtime (wrong results,
  network or API changes) are out of scope.
- **Local-module imports aren't checked.** It doesn't spot notebooks in subfolders importing repo-root modules
  without a `sys.path` change; this is the GenoTEX miss above.
- **R support is regex-based.** Complex R metaprogramming can be missed.
- **Some findings are debatable,** about 14% (see above). A human should skim each report before it is sent to
  an author.
- **Sample size.** Precision was measured on 304 hand-labelled findings in total. That is enough to catch common
  failure modes, not rare ones.
