import json
import textwrap
from pathlib import Path

import pytest

from repro_debt.checks import run_checks
from repro_debt.repo import load_repo


def notebook(cells, language="python"):
    """cells: list of (source, execution_count, outputs) or ("md", text)."""
    out = []
    for c in cells:
        if c[0] == "md":
            out.append({"cell_type": "markdown", "metadata": {}, "source": c[1]})
            continue
        src, count = c[0], c[1]
        outputs = c[2] if len(c) > 2 else []
        out.append({"cell_type": "code", "metadata": {}, "execution_count": count, "outputs": outputs,
                    "source": src})
    return json.dumps({
        "cells": out,
        "metadata": {"kernelspec": {"language": language, "name": language},
                     "language_info": {"name": language, "version": "3.10.4"}},
        "nbformat": 4, "nbformat_minor": 5,
    })


CLEAN_README = """# Study
Data availability: the data is on Zenodo (doi:10.5281/zenodo.123).

## How to reproduce
```
pip install -r requirements.txt
python analysis.py
```
"""


@pytest.fixture
def make_repo(tmp_path):
    def _make(files, base=True):
        if base:
            files = {"README.md": CLEAN_README, "LICENSE": "MIT", "requirements.txt": "numpy==1.26.4\n",
                     ".python-version": "3.11\n", **files}
        for rel, content in files.items():
            if content is None:
                continue
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(textwrap.dedent(content) if isinstance(content, str) else content)
        return tmp_path
    return _make


@pytest.fixture
def scan(make_repo):
    def _scan(files, base=True):
        root = make_repo(files, base)
        return run_checks(load_repo(str(root)))
    return _scan


def checks_of(result, check=None):
    ids = [f.check for f in result.findings]
    return ids if check is None else [f for f in result.findings if f.check == check]
