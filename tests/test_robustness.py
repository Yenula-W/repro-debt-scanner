"""Messy inputs seen in real repos must never crash the scanner."""
import json
import os

import pytest

from conftest import checks_of, notebook
from repro_debt.checks import run_checks
from repro_debt.repo import load_repo


def _scan_dir(root):
    return run_checks(load_repo(str(root)))


def test_empty_repo(tmp_path):
    r = _scan_dir(tmp_path)
    assert r.findings is not None


def test_repo_with_only_readme(tmp_path):
    (tmp_path / "README.md").write_text("# hi\n")
    assert checks_of(_scan_dir(tmp_path), "DEP001") == []  # no code, nothing to install


@pytest.mark.parametrize("content", [
    b"\xff\xfe\x00garbage\x00",                       # binary pretending to be .py
    "x = 'café'\n".encode("latin-1"),           # non-UTF8 source
    b"def broken(:\n    pass\n",                        # syntax error
    b"",                                                # empty file
])
def test_weird_python_files(tmp_path, content):
    (tmp_path / "run.py").write_bytes(content)
    _scan_dir(tmp_path)


@pytest.mark.parametrize("raw", [
    "not json at all",
    "[]",
    json.dumps({"cells": "nope"}),
    json.dumps({"cells": [{"cell_type": "code", "source": None, "execution_count": "x", "outputs": None}]}),
    json.dumps({"cells": [{"cell_type": "code", "source": ["x=1"], "execution_count": 1,
                           "outputs": ["str", None, {"output_type": "error"}, {"ename": 5, "traceback": "x"}]}]}),
    json.dumps({"cells": [None, 5, {"cell_type": "markdown"}], "metadata": None}),
    json.dumps({"worksheets": [{"cells": [{"cell_type": "code", "input": "import os"}]}], "nbformat": 3}),
])
def test_malformed_notebooks(tmp_path, raw):
    (tmp_path / "nb.ipynb").write_text(raw)
    _scan_dir(tmp_path)


def test_notebook_with_magics_and_shell(tmp_path):
    (tmp_path / "nb.ipynb").write_text(notebook([
        ("%matplotlib inline\n%load_ext autoreload\n!ls -la\nimport os", 1),
        ("%%bash\necho hi > out.txt", 2),
        ("x = !pwd\nprint(x)", 3),
    ]))
    r = _scan_dir(tmp_path)
    assert checks_of(r, "NB003") == []  # magics are not undefined names


def test_symlink_loop_and_broken_link(tmp_path):
    (tmp_path / "a").mkdir()
    os.symlink(tmp_path / "a", tmp_path / "a" / "loop")
    os.symlink(tmp_path / "missing", tmp_path / "dangling.py")
    _scan_dir(tmp_path)


def test_corrupt_archive_is_ignored(tmp_path):
    (tmp_path / "data.zip").write_bytes(b"PK\x03\x04 not really a zip")
    (tmp_path / "data.tar.gz").write_bytes(b"\x1f\x8b broken")
    _scan_dir(tmp_path)


def test_huge_file_is_skipped_not_loaded(tmp_path):
    (tmp_path / "big.py").write_text("x = 1\n" * 500_000)  # ~3 MB, over the code size cap
    _scan_dir(tmp_path)


def test_r_only_repo(tmp_path):
    (tmp_path / "DESCRIPTION").write_text("Package: x\nImports:\n    dplyr\n")
    (tmp_path / "a.R").write_text("library(dplyr)\nlibrary(ggplot2)\nx <- read.csv('in.csv')\n")
    r = _scan_dir(tmp_path)
    assert [f.detail for f in checks_of(r, "DEP003")] == ["ggplot2"]
    assert len(checks_of(r, "DATA001")) == 1


def test_r_notebook_kernel(tmp_path):
    (tmp_path / "nb.ipynb").write_text(notebook([("library(ggplot2)\nx <- 1", 1)], language="R"))
    _scan_dir(tmp_path)


def test_deeply_nested_and_unicode_paths(tmp_path):
    d = tmp_path / "données" / "分析" / ("deep/" * 20)
    d.mkdir(parents=True)
    (d / "run.py").write_text("open('résultats.csv')\n")
    _scan_dir(tmp_path)


def test_skips_vendored_dirs(tmp_path):
    for skip in ("node_modules/x", ".git/y", "venv/lib", ".ipynb_checkpoints"):
        p = tmp_path / skip
        p.mkdir(parents=True)
        (p / "bad.py").write_text("open('/Users/me/secret.csv')\n")
    assert checks_of(_scan_dir(tmp_path), "PATH001") == []


def test_scanned_code_warnings_are_not_printed(tmp_path, recwarn):
    (tmp_path / "a.py").write_text('p = "D:\\Learning\\x.tif"\n')
    run_checks(load_repo(str(tmp_path)))
    assert not [w for w in recwarn if issubclass(w.category, SyntaxWarning)]
