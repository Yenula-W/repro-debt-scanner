import json

from repro_debt.cli import main
from repro_debt.model import CHECKS, Finding
from repro_debt.report import score, top_fixes


def test_cli_writes_reports_and_fails_above(make_repo, tmp_path, capsys):
    root = make_repo({"run.py": 'import pandas\nopen("/Users/x/a.csv")\n'}, base=False)
    md, js = tmp_path / "r.md", tmp_path / "r.json"
    code = main(["scan", str(root), "--md", str(md), "--json", str(js), "--fail-above", "5",
                 "--github-annotations"])
    out = capsys.readouterr().out
    assert code == 1
    assert "# Reproducibility debt report" in md.read_text()
    data = json.loads(js.read_text())
    assert data["score"]["debt"] > 5 and len(data["top_fixes"]) <= 5
    assert "::error file=run.py,line=2" in out


def test_cli_passes_when_under_threshold(make_repo):
    root = make_repo({})
    assert main(["scan", str(root), "-q", "--fail-above", "100"]) == 0


def test_score_caps_repeated_findings():
    fs = [Finding("DEP003", "x", detail=str(i)) for i in range(10)] + [Finding("DOC001", "y")]
    sc = score(fs)
    assert sc["by_check"] == {"DEP003": 12, "DOC001": 10}
    assert sc["debt"] == 22 and sc["grade"] == "C"
    fixes = top_fixes(fs, sc["by_check"])
    assert fixes[0]["check"] == "DEP003" and "and 6 more" in fixes[0]["fix"]


def test_every_check_has_fix_text():
    for c in CHECKS.values():
        assert c.fix and c.severity in ("high", "medium", "low")
