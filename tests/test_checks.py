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
    r = scan({"requirements.txt": None, "DESCRIPTION": "Package: p\nImports: dplyr\nSuggests: dplyr, knitr\n",
              "a.R": "library(dplyr)\n"})
    assert "2 of 2 packages" in checks_of(r, "DEP002")[0].message


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
