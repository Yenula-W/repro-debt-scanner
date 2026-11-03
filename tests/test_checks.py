from conftest import checks_of, notebook


# ---------------------------------------------------------------- clean baseline

def test_clean_repo_has_no_findings(scan):
    r = scan({
        "data/input.csv": "a,b\n1,2\n",
        "analysis.py": """
            import numpy as np
            np.random.seed(0)
            x = np.loadtxt("data/input.csv", delimiter=",", skiprows=1)
            print(np.random.rand(3))
        """,
    })
    assert checks_of(r) == []
    assert [s.status for s in r.steps] == ["runnable"]


# ---------------------------------------------------------------- dependencies

def test_dep001_no_dependency_file(scan):
    r = scan({"requirements.txt": None, "run.py": "import pandas\nimport os\n"}, base=False)
    f = checks_of(r, "DEP001")
    assert len(f) == 1 and "pandas" in f[0].message and "os" not in f[0].detail


def test_dep002_unpinned(scan):
    r = scan({"requirements.txt": "numpy==1.0\npandas\nscipy>=1.2\n", "run.py": "import numpy, pandas, scipy\n"})
    f = checks_of(r, "DEP002")
    assert len(f) == 1 and f[0].file == "requirements.txt" and f[0].line == 2
    assert "pandas" in f[0].message and "scipy" in f[0].message


def test_dep002_skipped_with_lockfile(scan):
    r = scan({"requirements.txt": "pandas\n", "poetry.lock": "", "run.py": "import pandas\n"})
    assert checks_of(r, "DEP002") == []


def test_dep003_undeclared_import_with_alias_and_local_modules(scan):
    r = scan({
        "requirements.txt": "scikit-learn==1.4\nnumpy==1.26\n",
        "helpers/__init__.py": "",
        "utils.py": "",
        "run.py": "import sklearn\nimport numpy\nimport seaborn as sns\nfrom helpers import x\nimport utils\nimport json\n",
    })
    f = checks_of(r, "DEP003")
    assert [x.detail for x in f] == ["seaborn"]
    assert f[0].file == "run.py" and f[0].line == 3


def test_dep_environment_yml(scan):
    r = scan({
        "requirements.txt": None, ".python-version": None,
        "environment.yml": "name: x\ndependencies:\n  - python=3.10\n  - numpy=1.26\n  - pandas\n  - pip:\n    - torch==2.1\n",
        "run.py": "import numpy, pandas, torch\n",
    })
    assert checks_of(r, "DEP003") == []
    assert checks_of(r, "ENV001") == []
    assert "pandas" in checks_of(r, "DEP002")[0].message


def test_env001_python_version(scan):
    r = scan({".python-version": None, "run.py": "import numpy\n"})
    assert len(checks_of(r, "ENV001")) == 1


# ---------------------------------------------------------------- paths & data

def test_path001_absolute_paths(scan):
    r = scan({"run.py": 'import numpy as np\nnp.loadtxt("/Users/alice/proj/data.csv")\nX = r"C:\\\\data\\\\x.csv"\n'})
    f = checks_of(r, "PATH001")
    details = sorted(x.detail for x in f)
    assert details[0] == "/Users/alice/proj/data.csv" and details[1].startswith("C:")
    assert f[0].line in (2, 3)
    assert checks_of(r, "DATA001") == []  # absolute paths are not double-counted


def test_data001_missing_input_resolves_constants(scan):
    r = scan({"src/run.py": """
        import pandas as pd
        from pathlib import Path
        DATA = "data"
        df = pd.read_csv(Path(DATA) / "raw.csv")
        cfg = open("config.yaml")
        ok = pd.read_csv("present.csv")
        out = pd.read_csv("https://example.org/x.csv")
    """, "requirements.txt": "pandas==2.0\n", "present.csv": "a\n1\n"})
    f = checks_of(r, "DATA001")
    assert sorted(x.detail for x in f) == ["config.yaml", "data/raw.csv"]
    assert r.steps[0].status == "blocked" and r.steps[0].likely_break == "data"


def test_wf001_intermediate_step_undocumented(scan):
    files = {
        "requirements.txt": "pandas==2.0\n",
        "raw.csv": "a\n1\n",
        "clean.py": 'import pandas as pd\npd.read_csv("raw.csv").to_csv("clean.csv")\n',
        "model.py": 'import pandas as pd\ndf = pd.read_csv("clean.csv")\n',
    }
    r = scan(files)
    f = checks_of(r, "WF001")
    assert len(f) == 1 and f[0].file == "model.py" and "clean.py" in f[0].message
    assert checks_of(r, "DATA001") == []
    step = {s.file: s for s in r.steps}["model.py"]
    assert step.status == "needs-upstream" and step.upstream == ["clean.py"]


def test_wf001_suppressed_by_makefile(scan):
    r = scan({
        "requirements.txt": "pandas==2.0\n", "Makefile": "all:\n\tpython clean.py\n\tpython model.py\n",
        "clean.py": 'import pandas as pd\npd.DataFrame().to_csv("clean.csv")\n',
        "model.py": 'import pandas as pd\ndf = pd.read_csv("clean.csv")\n',
    })
    assert checks_of(r, "WF001") == []


# ---------------------------------------------------------------- randomness

def test_rand001_unseeded(scan):
    r = scan({"requirements.txt": "numpy==1\nscikit-learn==1\n", "run.py": """
        import numpy as np
        from sklearn.model_selection import train_test_split
        x = np.random.rand(10)
        a, b = train_test_split(x)
    """})
    f = checks_of(r, "RAND001")
    assert len(f) == 1 and f[0].line == 4


def test_rand001_seeded_or_random_state(scan):
    r = scan({"requirements.txt": "numpy==1\nscikit-learn==1\n", "a.py": """
        import numpy as np
        rng = np.random.default_rng(42)
        x = rng.normal(size=3)
    """, "b.py": """
        from sklearn.model_selection import train_test_split
        a, b = train_test_split([1, 2, 3], random_state=0)
    """})
    assert checks_of(r, "RAND001") == []


# ---------------------------------------------------------------- notebooks

def test_nb001_out_of_order(scan):
    nb = notebook([("import numpy as np", 3), ("x = np.zeros(2)", 1), ("print(x)", 2)])
    r = scan({"a.ipynb": nb})
    f = checks_of(r, "NB001")
    assert len(f) == 1 and f[0].cell == 2


def test_nb002_defined_later_and_nb003_never_defined(scan):
    nb = notebook([
        ("md", "# title"),
        ("import numpy as np\nprint(df.shape)\ny = undefined_thing + 1", 1),
        ("%matplotlib inline\ndf = np.zeros((2, 2))\n[i for i in range(3)]", 2),
        ("def f(a):\n    return a + local_only\nprint(f(1))", 3),
    ])
    r = scan({"a.ipynb": nb})
    nb2 = checks_of(r, "NB002")
    nb3 = checks_of(r, "NB003")
    assert [x.detail for x in nb2] == ["a.ipynb:df"] and nb2[0].cell == 2 and nb2[0].line == 2
    assert [x.detail for x in nb3] == ["a.ipynb:undefined_thing"]  # function-local names are not flagged
    assert r.steps[0].likely_break == "code"


def test_nb003_suppressed_after_star_import(scan):
    nb = notebook([("from pylab import *", 1), ("plot(x)", 2)])
    r = scan({"a.ipynb": nb, "requirements.txt": "matplotlib==3\n"})
    assert checks_of(r, "NB003") == []


def test_nb004_non_linear_outputs(scan):
    out = [{"output_type": "stream", "name": "stdout", "text": "1"}]
    nb = notebook([("x = 1", 5), ("print(x)", 9, out), ("y = 2", None)])
    r = scan({"a.ipynb": nb})
    f = checks_of(r, "NB004")
    assert len(f) == 1 and "first run number is 5" in f[0].message and "never run" in f[0].message


def test_nb005_saved_errors_are_classified(scan):
    err = [{"output_type": "error", "ename": "ModuleNotFoundError", "evalue": "No module named 'foo'",
            "traceback": []}]
    nb = notebook([("import foo", 1, err)])
    r = scan({"a.ipynb": nb, "requirements.txt": "foo==1\n"})
    f = checks_of(r, "NB005")
    assert len(f) == 1 and f[0].category == "dependency"
    assert r.steps[0].likely_break == "dependency"


def test_r_notebook_and_cell_magics_do_not_crash(scan):
    nb = notebook([("%%bash\nls", 1), ("x <- 1", 2)], language="R")
    r = scan({"a.ipynb": nb})
    assert "NB003" not in checks_of(r)


# ---------------------------------------------------------------- figures

def test_fig001_orphan_figures(scan):
    r = scan({
        "figures/fig1.png": "x", "figures/fig2.png": "x",
        "requirements.txt": "matplotlib==3\n",
        "plot.py": 'import matplotlib.pyplot as plt\nplt.savefig("figures/fig1.png")\n',
    })
    f = checks_of(r, "FIG001")
    assert len(f) == 1 and "fig2.png" in f[0].message and "fig1.png" not in f[0].message


# ---------------------------------------------------------------- docs

def test_doc_checks(scan):
    r = scan({"run.py": 'import json\njson.load(open("data.json"))\n'}, base=False)
    ids = set(checks_of(r))
    assert {"DOC001", "DOC003", "DOC004"} <= ids


def test_doc002_readme_without_instructions(scan):
    r = scan({"README.md": "# My project\nThis code does science.\n"})
    assert len(checks_of(r, "DOC002")) == 1


def test_doc004_satisfied_by_data_readme(scan):
    r = scan({"README.md": "# x\n```\npython run.py\n```\n", "data/README.md": "where data lives",
              "run.py": 'import json\njson.load(open("data/a.json"))\n'})
    assert checks_of(r, "DOC004") == []


# ---------------------------------------------------------------- R

def test_r_script(scan):
    r = scan({"requirements.txt": None, "analysis.R": """
        library(dplyr)
        library(stats)
        df <- read.csv("data/missing.csv")
        x <- sample(1:10)
        p <- "C:/Users/bob/file.txt"
        ggplot2::ggplot(df)
    """})
    ids = checks_of(r)
    assert "DEP001" in ids and "dplyr" in checks_of(r, "DEP001")[0].message
    assert "stats" not in checks_of(r, "DEP001")[0].message
    assert "DATA001" in ids and "RAND001" in ids and "PATH001" in ids


def test_r_description_declares_packages(scan):
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: x\nImports: dplyr (>= 1.0),\n  ggplot2\nLicense: MIT\n",
              "analysis.R": "set.seed(1)\nlibrary(dplyr)\nlibrary(tidyr)\nx <- sample(1:3)\n"})
    assert [f.detail for f in checks_of(r, "DEP003")] == ["tidyr"]
    assert checks_of(r, "RAND001") == []


# ---------------------------------------------------------------- regressions from real repos

def test_downloaded_files_are_not_missing(scan):
    nb = notebook([
        ("!wget https://example.org/files/a.csv", 1),
        ("!curl -o b.csv https://example.org/x", 2),
        ("import wget\nwget.download('https://example.org/c.csv')", 3),
        ("from urllib.request import urlretrieve\nurlretrieve('https://x.org/q', 'd.csv')", 4),
        ("import numpy as np\nfor f in ['a.csv']: pass\nnp.loadtxt('a.csv'); np.loadtxt('b.csv')\n"
         "np.loadtxt('c.csv'); np.loadtxt('d.csv')", 5),
    ])
    r = scan({"a.ipynb": nb, "requirements.txt": "numpy==1\nwget==3\n"})
    assert checks_of(r, "DATA001") == []


def test_relative_path_matching_other_working_dir(scan):
    # R packages: code in R/ reads "data/x.csv" relative to vignettes/
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: mypkg\nImports: dplyr\nLicense: MIT\n",
              "vignettes/data/x.csv": "a\n", "R/functions.R": 'f <- function() read.csv("data/x.csv")\n',
              "vignettes/report.Rmd": "```{r}\nlibrary(mypkg)\nlibrary(dplyr)\n```\n"})
    assert checks_of(r, "DATA001") == []
    assert checks_of(r, "DEP003") == []


def test_dep002_counts_unique_packages(scan):
    r = scan({"requirements.txt": "dplyr\nknitr\ndplyr\n", "run.py": "import os\n"})
    assert "2 of 2 packages" in checks_of(r, "DEP002")[0].message


def test_dep002_skips_r_description_minimum_versions(scan):
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: p\nImports: dplyr\nSuggests: knitr\n",
              "a.R": "library(dplyr)\n"})
    assert checks_of(r, "DEP002") == []


# ---------------------------------------------------------------- false alarms found on real paper repos

def test_data001_files_inside_bundled_zip_count_as_present(make_repo):
    import zipfile
    from repro_debt.checks import run_checks
    from repro_debt.repo import load_repo
    root = make_repo({"notebooks/figs.py": 'import pandas as pd\npd.read_csv("../data/table.csv")\n',
                      "requirements.txt": "pandas==2.2.0\n"})
    with zipfile.ZipFile(root / "data.zip", "w") as z:
        z.writestr("data/table.csv", "a\n1\n")
    assert checks_of(run_checks(load_repo(str(root))), "DATA001") == []


def test_data001_skips_paths_a_shell_script_creates(scan):
    r = scan({"test.sh": "gpu-coloc -r --results example/example_results.tsv\n",
              "plot.py": 'import pandas as pd\npd.read_csv("example/example_results.tsv")\n',
              "requirements.txt": "pandas==2.2.0\n"})
    assert checks_of(r, "DATA001") == []


def test_data001_still_flags_undocumented_missing_file(scan):
    r = scan({"plot.py": 'import pandas as pd\npd.read_csv("secret/raw.csv")\n',
              "requirements.txt": "pandas==2.2.0\n"})
    assert len(checks_of(r, "DATA001")) == 1


def test_dep003_ignores_setuptools_in_setup_py(scan):
    r = scan({"setup.py": "from setuptools import setup\nsetup(name='x')\n"})
    assert checks_of(r, "DEP003") == []


def test_dep003_conda_r_package_names(scan):
    r = scan({"environment.yml": "dependencies:\n  - r-ggplot2=3.5.0\n  - bioconductor-deseq2=1.42.0\n",
              "fig.R": "library(ggplot2)\nlibrary(DESeq2)\n"})
    assert checks_of(r, "DEP003") == []


def test_dep001_conda_env_with_unusual_name_counts(scan):
    r = scan({"requirements.txt": None, "requirements.yml": "name: x\ndependencies:\n  - numpy=1.26.4\n",
              "run.py": "import numpy\n"})
    assert checks_of(r, "DEP001") == [] and checks_of(r, "DEP003") == []


def test_data001_mentions_linked_deposit(scan):
    r = scan({"README.md": "# x\nRun `python plot.py`. Data: https://zenodo.org/records/1\n",
              "plot.py": 'import numpy as np\nnp.loadtxt("results/r1.csv")\n'})
    f = checks_of(r, "DATA001")
    assert len(f) == 1 and "zenodo.org" in f[0].message


def test_dep001_colab_pip_install_counts_as_declared(scan):
    r = scan({"requirements.txt": None,
              "colab.ipynb": notebook([("!pip install biopython==1.83 pandas", 1), ("import Bio\nimport pandas", 2)])})
    assert checks_of(r, "DEP001") == [] and checks_of(r, "DEP003") == []
    assert any("pandas" in f.message for f in checks_of(r, "DEP002"))


def test_rand001_skips_library_modules_and_tests(scan):
    r = scan({"pkg/__init__.py": "", "pkg/aug.py": "import random\ndef jitter(x):\n    return x + random.random()\n",
              "tests/test_aug.py": "import random\nrandom.random()\n",
              "requirements.txt": "numpy==1.26.4\n"})
    assert checks_of(r, "RAND001") == []


def test_nb003_question_mark_in_comment_is_not_ipython_help(scan):
    r = scan({"nb.ipynb": notebook([("fold=1 # which fold to look at?\nprint(fold)", 1)])})
    assert checks_of(r, "NB003") == []


def test_nb_unparseable_cell_still_defines_names(scan):
    # a cell this Python can't parse (here: a stray bracket) must not make later cells look undefined
    r = scan({"nb.ipynb": notebook([("sched = make()\nx = f'{sched[\"a\"}'", 1), ("print(sched)", 2)])})
    assert checks_of(r, "NB003") == [] and checks_of(r, "NB002") == []


def test_data001_ignores_importlib_metadata_read_text(scan):
    r = scan({"run.py": "from importlib import metadata\nmetadata.distribution('x').read_text('direct_url.json')\n"})
    assert checks_of(r, "DATA001") == []


def test_nb005_keyboard_interrupt_is_not_called_a_code_problem(scan):
    err = [{"output_type": "error", "ename": "KeyboardInterrupt", "evalue": "", "traceback": []}]
    r = scan({"nb.ipynb": notebook([("import time\ntime.sleep(9)", 1, err)])})
    f = checks_of(r, "NB005")
    assert len(f) == 1 and "interrupted" in f[0].message and "code problem" not in f[0].message


def test_fig001_ignores_logos_and_package_docs(scan):
    r = scan({"figures/logo.png": "x", "man/figures/plot.png": "x", "figures/fig2.png": "x"})
    f = checks_of(r, "FIG001")
    assert len(f) == 1 and "fig2.png" in f[0].message and "logo" not in f[0].message


def test_doc004_only_when_inputs_are_missing(scan):
    readme = "# x\n```\npython run.py\n```\n"
    present = scan({"README.md": readme, "data/a.csv": "1\n", "run.py": "open('data/a.csv')\n"})
    missing = scan({"README.md": readme, "run.py": "open('data/b.csv')\n"})
    assert checks_of(present, "DOC004") == [] and len(checks_of(missing, "DOC004")) == 1


def test_snakemake_env_files_count_as_dependencies(scan):
    r = scan({"requirements.txt": None, "workflow/envs/general.yaml": "channels:\n  - conda-forge\ndependencies:\n  - scipy=1.11\n",
              "workflow/scripts/a.py": "import scipy\n"})
    assert checks_of(r, "DEP001") == [] and checks_of(r, "DEP003") == []


def test_pip_install_from_git_url_is_not_a_package_name(scan):
    r = scan({"requirements.txt": None, "nb.ipynb": notebook([("!pip install git+https://github.com/a/b.git pyfaidx==0.8", 1)])})
    assert all("git" not in f.message for f in checks_of(r, "DEP002"))


def test_dep002_skips_library_metadata_and_dev_requirements(scan):
    r = scan({"requirements.txt": None, "pyproject.toml": '[project]\nname="x"\ndependencies = ["numpy>=1.2"]\n',
              "requirements-dev.txt": "pytest\n", "run.py": "import numpy\n"})
    assert checks_of(r, "DEP002") == []


def test_r_requirenamespace_with_variable_is_not_a_package(scan):
    r = scan({"DESCRIPTION": "Package: p\nImports: dplyr\n",
              "R/a.R": "f <- function(package) requireNamespace(package, quietly = TRUE)\nrequireNamespace('dplyr')\n"})
    assert checks_of(r, "DEP003") == []


def test_data001_files_in_a_tools_output_dir_are_produced(scan):
    r = scan({"nb.ipynb": notebook([("from pathlib import Path\nimport envoi, pandas as pd\nOUT = Path('walk_out')\n"
                                     "envoi.extract(points, output_dir=OUT)\npd.read_csv(OUT / 'stats.csv')", 1)]),
              "requirements.txt": "pandas==2.2.0\nenvoi==1.0\n"})
    assert checks_of(r, "DATA001") == []


def test_path001_skips_single_home_folder(scan):
    r = scan({"run.py": "import os\nos.makedirs(os.path.expanduser('~/envoi_outputs'))\nopen('~/proj/data/x.csv')\n"})
    assert [f.detail for f in checks_of(r, "PATH001")] == ["~/proj/data/x.csv"]


def test_fig001_skips_images_shown_in_readme(scan):
    r = scan({"README.md": "# x\n![overview](image/fig_main.png)\n```\npython run.py\n```\n", "image/fig_main.png": "x"})
    assert checks_of(r, "FIG001") == []


def test_utf16_requirements_from_powershell(make_repo):
    from repro_debt.checks import run_checks
    from repro_debt.repo import load_repo
    root = make_repo({"run.py": "import numpy\n", "requirements.txt": None})
    (root / "requirements.txt").write_bytes("numpy==1.24.1\r\n".encode("utf-16"))
    r = run_checks(load_repo(str(root)))
    assert checks_of(r, "DEP001") == [] and checks_of(r, "DEP003") == []


def test_hydra_is_installed_as_hydra_core(scan):
    r = scan({"requirements.txt": "hydra-core==1.3.2\n", "run.py": "from hydra.utils import instantiate\n"})
    assert checks_of(r, "DEP003") == []


def test_path_open_mode_is_not_a_file(scan):
    r = scan({"run.py": "from pathlib import Path\nwith Path('README.md').open('r+') as f:\n    f.read()\n"})
    assert checks_of(r, "DATA001") == []


def test_marimo_exports_are_skipped(scan):
    r = scan({"__marimo__/t.ipynb": notebook([("print(x)", 1), ("x = 1", 2)])})
    assert checks_of(r, "NB002") == []


def test_readme_rmd_install_commands_are_not_dependencies(scan):
    r = scan({"DESCRIPTION": "Package: p\nImports: dplyr\n", "README.Rmd": "```{r}\nremotes::install_github('a/b')\n```\n",
              "R/a.R": "library(dplyr)\n"})
    assert checks_of(r, "DEP003") == []


# ---------------------------------------------------------------- ship-bar round A regressions

def test_method_open_mode_is_not_a_path(scan):
    r = scan({"requirements.txt": None, "pyproject.toml": '[project]\nname="x"\ndependencies=[]\nrequires-python=">=3.9"\n',
              "x/run.py": 'import os\nfrom pathlib import Path\n'
                          'def f(stdout, tmp):\n'
                          '    with (stdout or Path(os.devnull)).open("wb") as fh: pass\n'
                          '    with (tmp / "a").open("r+b") as fh: pass\n'
                          '    Path("missing.txt").open("r")\n'})
    assert [f.detail for f in checks_of(r, "DATA001")] == ["missing.txt"]


def test_pyproject_arrays_with_extras_and_dependency_groups(scan):
    r = scan({"requirements.txt": None, "pyproject.toml": """
        [project]
        name = "atlas"
        requires-python = ">=3.10"
        dependencies = [
            "botocore[crt]>=1.4",  # brackets ] inside
            "scikit-learn>=1.9",
        ]

        [dependency-groups]
        dev = ["pytest>=8"]
        report = ["jinja2>=3.1"]

        [tool.poetry.group.docs.dependencies]
        sphinx = "^7"
    """, "run.py": "import sklearn, pytest, jinja2, botocore, sphinx\n"})
    assert checks_of(r, "DEP003") == []


def test_env_yml_pip_options_are_not_packages(scan):
    r = scan({"requirements.txt": None, "environment.yml":
              "dependencies:\n  - python=3.11\n  - numpy=1.26\n  - pip:\n    - --extra-index-url https://x.org\n    - torch==2.1\n",
              "run.py": "import numpy, torch\n"})
    assert checks_of(r, "DEP002") == []


def test_path001_ignores_test_fixtures(scan):
    r = scan({"tests/test_paths.py": 'assert f("C:\\\\data\\\\a.zarr")\nassert g("/home/user/x")\n',
              "tests/testthat/test-a.R": 'expect_equal(f("C:/p/a.wav"), "a")\n',
              "run.py": 'open("/Users/alice/data.csv")\n'})
    assert [f.file for f in checks_of(r, "PATH001")] == ["run.py"]


def test_r_withr_seed_counts_as_seed(scan):
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: p\nImports: withr\nLicense: MIT\nDepends: R (>= 4.1)\n",
              "analysis.R": "ids <- withr::with_seed(1, sample(1:10))\n"})
    assert checks_of(r, "RAND001") == []


def test_nb005_data_errors_and_deliberate_errors(scan):
    def err(ename, evalue):
        return [{"output_type": "error", "ename": ename, "evalue": evalue, "traceback": []}]
    nb = notebook([
        ("import geopandas as gpd\ngpd.read_file('x.shp')", 1, err("DataSourceError", "x.shp: No such file or directory")),
        ("md", "The method will fail if the series overlap:"),
        ("ts.concatenate(other)", 2, err("ValueError", "GTIs must be mutually exclusive")),
        ("# This will fail\nf([1])", 3, err("TypeError", "bad")),
    ])
    r = scan({"a.ipynb": nb, "requirements.txt": "geopandas==1\n"})
    f = checks_of(r, "NB005")
    assert len(f) == 1 and f[0].cell == 1 and f[0].category == "data"


def test_wf001_needs_matching_folders_not_just_file_name(scan):
    r = scan({"requirements.txt": "pandas==2\n",
              "scripts/eval.R": 'write.csv(df, "output/hospital.csv")\n',
              "scripts/report.py": 'import pandas as pd\npd.read_csv("target-data/hospital.csv")\n'})
    assert checks_of(r, "WF001") == []
    assert [f.detail for f in checks_of(r, "DATA001")] == ["target-data/hospital.csv"]


def test_env001_satisfied_by_ci_python_version(scan):
    r = scan({".python-version": None, "run.py": "import numpy\n",
              ".github/workflows/ci.yml": "jobs:\n  t:\n    steps:\n      - uses: actions/setup-python@v5\n        with: { python-version: '3.12' }\n"})
    assert checks_of(r, "ENV001") == []


def test_notebook_names_defined_through_magics_and_broken_cells(scan):
    nb = notebook([
        ("from shapely.geometry import Point\nimport warnings\nprint(x))", 1),  # unparseable cell
        ("%memit ps_it = make()\n%time y = 2", 2),
        ("print(Point, ps_it, y)", 3),
    ])
    r = scan({"a.ipynb": nb, "requirements.txt": "shapely==2\n"})
    assert checks_of(r, "NB003") == [] and checks_of(r, "NB002") == []


# ---------------------------------------------------------------- ship-bar round B regressions

def test_computed_output_names_count_as_produced(scan):
    r = scan({"requirements.txt": "xarray==2024.1\n",
              "build_stack.py": 'import xarray as xr\nfor year in (2018, 2023):\n    out = xr.Dataset()\n'
                                '    out.to_netcdf(f"stack_{year}.nc")\n',
              "train.py": 'import xarray as xr\nref = xr.open_dataset("stack_2018.nc")\nx = xr.open_dataset("other.nc")\n'
                          'import pandas as pd\npd.DataFrame().to_csv(f"{x}.csv")\n'})
    assert [f.detail for f in checks_of(r, "DATA001")] == ["other.nc"]  # "{x}.csv" is too generic to match
    assert [f.detail for f in checks_of(r, "WF001")] == ["build_stack.py -> train.py"]


def test_google_colab_is_not_a_dependency(scan):
    nb = notebook([("from google.colab import userdata, drive\nimport google.colab", 1)])
    r = scan({"a.ipynb": nb})
    assert checks_of(r, "DEP003") == []


def test_doc004_data_in_repo_or_public_platform(scan):
    for readme in ("# x\n```\npython run.py\n```\nReads `final.xlsx`, the cleaned dataset in this repository.\n",
                   "# x\n```\npython run.py\n```\nImagery comes from Google Earth Engine and Planetary Computer.\n"):
        r = scan({"README.md": readme, "run.py": 'import json\njson.load(open("a.json"))\n'})
        assert checks_of(r, "DOC004") == [], readme


def test_path001_ignores_constants_appended_to_a_root(scan):
    r = scan({"run.py": 'V = get_root()\nSPLITS = (("train", V + "/data/train.csv"),)\np = f"{V}/home/x.csv"\n'
                        'q = "/data/real.csv"\n'})
    assert [f.detail for f in checks_of(r, "PATH001")] == ["/data/real.csv"]


# ---------------------------------------------------------------- ship-bar round C regressions

def test_path001_skips_program_files_and_url_routes(scan):
    r = scan({"run.py": 'from fastapi import APIRouter\nrouter = APIRouter()\n'
                        'DLL = r"C:\\Program Files\\SharpCap\\x64\\qhyccd.dll"\n'
                        '@router.get("/projects/{project_id}/revisions")\ndef f(): pass\n'
                        'API = "/data/items/{id}"\nREAL = "/data/lab/raw.csv"\n'})
    assert [f.detail for f in checks_of(r, "PATH001")] == ["/data/lab/raw.csv"]


def test_loop_built_output_names_are_produced(scan):
    nb = notebook([
        ("import pandas as pd\nfrom pathlib import Path\nOUT = Path('out')\n"
         "for name in ['res_a', 'res_b']:\n    pd.DataFrame().to_csv(OUT / f'{name}.csv')", 1),
        ("import pandas as pd\nx = pd.read_csv('out/res_b.csv')", 2),
    ])
    r = scan({"a.ipynb": nb, "requirements.txt": "pandas==2\n"})
    assert checks_of(r, "DATA001") == []


def test_r_computed_figure_names_suppress_fig001(scan):
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: p\nImports: ggplot2\nLicense: MIT\nDepends: R (>= 4)\n",
              "results/go_dotplot_0.pdf": "x",
              "pipeline.R": 'for (cl in 0:3) {\n  pdf(file.path(OUT_DIR, paste0("go_dotplot_", cl, ".pdf")))\n}\n'})
    assert checks_of(r, "FIG001") == []


def test_pywin32_modules_map_to_pywin32(scan):
    r = scan({"requirements.txt": "pywin32==306\n", "hw.py": "import pywintypes, win32con, pythoncom\n"})
    assert checks_of(r, "DEP003") == []


def test_doc004_provenance_section(scan):
    r = scan({"README.md": "# x\n```\npython run.py\n```\n## Data provenance\nA ClinVar extract, made with bcftools.\n",
              "run.py": 'open("data/v.vcf")\n'})
    assert checks_of(r, "DOC004") == []


def test_random_identifiers_are_not_results(scan):
    r = scan({"client.py": "import random, string\n"
                           "key = ''.join(random.choice('0123456789') for _ in range(19))\n"
                           "tok = random.choices(string.ascii_letters, k=8)\n"})
    assert checks_of(r, "RAND001") == []


def test_wf001_numbered_files_state_the_order(scan):
    files = {"requirements.txt": "scanpy==1\n",
             "notebooks/02_qc.py": 'import scanpy as sc\nsc.AnnData().write_h5ad("02_qc.h5ad")\n',
             "notebooks/03_annotate.py": 'import scanpy as sc\na = sc.read_h5ad("02_qc.h5ad")\n',
             "notebooks/plot.py": 'import scanpy as sc\na = sc.read_h5ad("02_qc.h5ad")\n'}
    r = scan(files)
    assert [f.file for f in checks_of(r, "WF001")] == ["notebooks/plot.py"]
