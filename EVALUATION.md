# Evaluation

Measured on 2026-11-02/03 against the shared adoption-ready bar (`~/Desktop/LabAdoption/ADOPTION_BAR.md`) and
then the stricter ship bar (`~/Desktop/LabAdoption/SHIP_BAR.md`, section 7).

Summary: **does not meet the ship bar.** None of the 3 allowed untouched rounds passed. As the bar requires, the
five checks still below 80% after the last round (PATH001, DATA001, WF001, FIG001, DOC004) are now **opt-in**
(`--all-checks`). The 13 on-by-default checks scored 98% and 96% in the last two rounds, but code changed between
those rounds, so they have not formally passed either. It remains fit for a **supervised pilot**: you run it and a
person skims each report before it goes to an author. Known gaps are listed at the end.

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

## 7. Ship-bar rounds (2026-11-03)

Rules (from `SHIP_BAR.md`):
- Each round uses 25 new public repos, never used before. They were drawn by GitHub topic search across 20 fields
  and excluded the 58-repo corpus, outreach batch 1 and the 4 development repos.
- The precision numbers below come from the **first run, before any change**.
- About 5 findings per check were hand-judged against the source. "Debatable" counts as passing.
- A round passes at ≥90% overall, no check below 80%, 0 crashes and 0 overstated claims.

The cap was 3 rounds.

| Round | Code under test | Repos | Crashes | Runtime (median / max) | Sample | Wrong | Debatable | Precision | Passed? |
|---|---|---|---|---|---|---|---|---|---|
| A | `b3a13da` | 25 | 0 | 0.3 s / 10.6 s | 69 | 19 | 7 | **72.5%** | no |
| B | `e32242a` | 25 | 0 | 0.2 s / 0.6 s | 67 | 7 | 5 | **89.6%** | no |
| C | `07436f3` | 25 | 0 | 0.2 s / 9.7 s | 68 | 14 | 8 | **79.4%** | no |

Per-check precision, untouched, as correct plus debatable out of the sample:

| Check | A | B | C | Default now |
|---|---|---|---|---|
| DEP001 | 4/4 | 5/5 | 5/5 | on |
| DEP002 | 4/5 | 5/5 | 5/5 | on |
| DEP003 | **2/5** | 4/5 | 4/5 | on |
| ENV001 | **2/5** | 5/5 | 5/5 | on |
| RAND001 | 4/5 | 5/5 | 4/5 | on |
| NB001 | 5/5 | 5/5 | 5/5 | on |
| NB002 | 3/3 | 1/1 | 3/3 | on |
| NB003 | **3/5** | 5/5 | 2/2 | on |
| NB004 | 5/5 | 5/5 | 5/5 | on |
| NB005 | 4/5 | 1/1 | 3/3 | on |
| DOC001 | n/a | n/a | n/a | on |
| DOC002 | 2/2 | 2/2 | 3/3 | on |
| DOC003 | 4/4 | 5/5 | 5/5 | on |
| PATH001 | **1/5** | 4/5 | **0/5** | **opt-in** |
| DATA001 | **3/5** | **2/5** | **3/5** | **opt-in** |
| WF001 | **3/5** | 5/5 | **2/5** | **opt-in** |
| FIG001 | n/a | 1/1 | **0/1** | **opt-in** |
| DOC004 | 1/1 | **0/2** | **0/1** | **opt-in** |

Precision of only the checks that are on by default:

| Round | Precision | Lowest check |
|---|---|---|
| A | 79% (42/53) | 40% |
| B | 98% (48/49) | DEP003 80% |
| C | 96% (49/51) | 80% |

Rounds B and C would both pass, but there was a code change between them, so the two-round streak isn't met.

**Wrong findings and their root-cause fixes.** Each fix has a regression test in `tests/test_checks.py`, in the
"ship-bar round A/B/C regressions" sections.

| Round | Wrong finding (example) | Fix |
|---|---|---|
| A | `.open("wb")` on `(stdout or Path(...))` read as a file named `wb` | A method `.open(mode)` takes the path from its receiver |
| A | `scikit-learn` in `pyproject.toml` not seen (the `botocore[crt]` brackets ended the list early); PEP 735 `[dependency-groups]` ignored | Quote-aware TOML array parsing; read dependency-groups, poetry groups and uv dev-dependencies |
| A | `--extra-index-url` reported as an unpinned package | Skip pip options in conda files |
| A | Made-up `C:\data\a.zarr` and `/home/user/x` in unit tests | No PATH001 in test files |
| A | `withr::with_seed(1, sample(...))` reported as unseeded | `with_seed`/`local_seed`/`set_random_seed` count as seeds |
| A | `DataSourceError: No such file` called a "code problem"; tutorial cells that fail on purpose | Classify from the error message; skip errors that the cell or the note above it says are deliberate |
| A | WF001 tied `target-data/x.csv` to a script writing `output/x.csv` (same file name only) | Match whole trailing path segments |
| A | ENV001 when CI pins `python-version: '3.12'` | GitHub workflow Python/R versions count as recorded |
| A | NB003 for `ps_it` set by `%memit ps_it = ...`, and for `Point` imported in a cell with a syntax error | Keep the statement after a line magic; fix the fallback regex for unparseable cells |
| B | DATA001 "no script creates it" for `stack_2018.nc` written by `f"stack_{year}.nc"` | Computed output names become glob patterns, kept only with a real stem of 3+ characters |
| B | `google.colab` reported as an undeclared package | Runtime-only modules are skipped |
| B | DOC004 although the README says the data is in the repo, or comes from Earth Engine/Planetary Computer | Recognise in-repo data and named public data platforms |
| B | `V + "/data/x.csv"` reported as an absolute path | Constants appended to another value are not absolute |
| C | `C:\Program Files\...\driver.dll` and `@router.get("/projects/{id}")` | Standard install folders, decorator route strings, and `/data/`, `/projects/` strings with no file extension are skipped |
| C | DATA001 for files a loop writes, e.g. `for name in [...]: to_csv(f"{name}.csv")` | Loop variables over literal lists are expanded |
| C | FIG001 for `pdf(file.path(OUT, paste0("go_dotplot_", cl, ".pdf")))` | R `paste0`/`file.path`/`sprintf` output names are patterns |
| C | `pywintypes` undeclared although `pywin32` is pinned | Module names mapped to pywin32 |
| C | DOC004 although the README has a "Data provenance" section (ClinVar) | Provenance and common database names recognised |
| C | RAND001 for `random.choice('0123456789')` that builds a multipart boundary | Random letters and digits are IDs, not results |
| C | WF001 for `02_qc.ipynb` → `03_annotate.ipynb` | Numbered file names already state the run order |

The round C fixes were not measured on a fresh round, because the cap was reached.

**Debatable findings (true, but arguably not worth fixing):**
- A: a `data-raw/` dev script reading an undeposited file; 3 tutorial or `KeyError` notebook errors; 2 noise
  functions inside an R package; a `scratch_*.py` WF001.
- B: an archived dev test; a Colab `!pip install` cell judged as a dependency file; `BiocManager`, which a script
  installs itself; 2 `torch.rand` dummy inputs in model files.
- C: 2 Colab `!pip install` cells; `matplotlib` pulled in by another declared package; `numpy` from Colab; a
  `data-raw/` example; a Selenium scraper error; joke-picking `random.choice`; a `torch.rand` benchmark input.

**Overstated claims.** Every wrong finding above is also an overstated claim, for example "no script creates it"
when one does. None of the messages calls a recommendation an "error".

**Clean install on the final commit.** `pip install git+https://github.com/Yenula-W/repro-debt-scanner` in fresh
venvs. Every README usage line was run verbatim against a copy of `examples/messy-lab-repo`.

| Python | pip | Install | README usage |
|---|---|---|---|
| 3.9.7 (macOS framework) | 21.2.3 | 8 s | all 8 lines OK: 10 findings by default, 15 with `--all-checks` (grade F), `--fail-above 25` exits 1 |
| 3.12.15 | 25.0.1 | 3 s | identical |
| 3.13.16 | 26.2.1 | 4 s | identical |

**Optional extras.** The scanner has no runtime dependencies and no optional extras; `[test]` only adds pytest. The
suite (103 tests) runs on a bare install plus pytest, so there is nothing to skip.

**CI.** Green on the final commit (tests on 3.9 and 3.12, plus the Action self-test). The repo is private.

Round inputs (GitHub `owner/repo`):
- A: Jin-HoMLee/splice-neoepitope-pipeline, Yunuuuu/rsahmi, soheil-mp/apus, AndrewVynnytskyi/SAR-Ship-Segmentation,
  utpalmtbi/intro_R_1, birdflow-science/BirdFlowR, DattaHub/inversemean, NygenAnalytics/CyteArc,
  Primordial-sim/primordial, Eomesodermin/TabulaSapiens_2022, ai4castinghub/hospitalization-forecast, jonatas/pg_bio,
  Emeric-FullStack/diy-eeg-bci, agent-engineering-studio/limen, spdr-lily/m.i.n.d,
  YashrajManan/Epidemic_Dynamics_Simulation, acm-research-f26/ATLAS, StingraySoftware/notebooks,
  bdgroves/project-ice-wave, jbferet/prosail, pradeeshwarrj/pamflow, tingtmu/Seq-Unit-01, hongjunt50-afk/shihai,
  morinlab/GAMBLR, Cupesi/bolivia-fire.
- B: meteostat/meteostat, now-i-know-my-abcd/docs, ofsoundmind/tree-tops, cerfacs-globc/idownscale, sappelhoff/pyprep,
  JitheshMithra/BINDops, masterA88/jaga-sawah, Shahab-Esfandiar/Landuse-Segmentation-Using-DeepLearning,
  k-wheeler/AppTrail_Phenology, Joshua-Anojulu/influenza-season-forecasting, AdilShamim8/NeuroBridge,
  stardust-452/portfolio, hendersontrent/mean-var-ts-classify, mhdf/uncertainty-based_model_transfer,
  Sherlock-Shi/BSc-Dissertation-Gaming-and-Executive-Function, Pritom-byte/ecosystem-population-dynamics-simulation,
  starsimhub/covasim, JUhalt/contentvalidR, pachadotdev/cp1919, YMa-lab/GESSO, openbraininstitute/entitysdk,
  HugoMachadoRodrigues/GeoVersa, BoogyMan-bot/sentinel-1-soil-moisture, jmponcebe/DengueMLOps,
  apace7/local_volume_database.
- C: EnriqueJ67/ScopePower, CTTIR/molpathR, StaGill/DenMark, bczernecki/climate, SattikBhaumik/Analyzing_Exoplanets,
  Goldi5/Raumklima-2, soroushdeimi/neuroSush, AungChitMoe1995/hiv-epidemiology-and-treatment-analytics,
  sofiajob/ATNF-pulsar-catalogue-analysis, LINZIQI24GITHUB/wechat-relationship-analysis, vhtkrk/mitsubishi_remote,
  sachitsatyal/Immunomap, HelmchenLabSoftware/K-mirror, northflowlabs/northflow-notebooks,
  AudtheiaOfficial/audtheia-v2, Empyrean-Dynamics/empyrean-scenarios, RoshaniPawar16/alphamissense-cftr,
  mahnoorrshahid/scrnaseq-breast-atlas, mbote-droid/counterscreen, leomorgzzz/vitiligo-linfocitos-t,
  yvesfurrer/Droughts-Coups, aqbilillah/IRT_Item-Response-Theory, gero-science/ct-validation,
  samanisrar200/Computational_Reanalysis_of_COVID-19_scRNA, ratschlab/DeepSpot.


## Known limitations

- **Ship bar not met.** No 2 untouched rounds in a row passed (section 7). The 5 data and workflow checks are
  opt-in. Enabling them by default needs a new untouched round, which is beyond the 3-round cap.

- **Static analysis only.** It never runs code, so problems that only appear at runtime (wrong results,
  network or API changes) are out of scope.
- **Local-module imports aren't checked.** It doesn't spot notebooks in subfolders importing repo-root modules
  without a `sys.path` change; this is the GenoTEX miss above.
- **R support is regex-based.** Complex R metaprogramming can be missed.
- **Some findings are debatable,** about 14% (see above). A human should skim each report before it is sent to
  an author.
- **Sample size.** Precision was measured on 304 hand-labelled findings in total. That is enough to catch common
  failure modes, not rare ones.
