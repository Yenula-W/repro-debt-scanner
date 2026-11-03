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
    assert "::error title=DEP001" in out and "::notice file=run.py,line=2,title=[needs review] PATH001" in out


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


def test_exclude(make_repo, capsys):
    root = make_repo({"vendor/x.py": 'open("/Users/x/a.csv")\n'})
    main(["scan", str(root), "--format", "json"])
    assert "PATH001" in capsys.readouterr().out
    main(["scan", str(root), "--format", "json", "--exclude", "vendor"])
    assert "PATH001" not in capsys.readouterr().out


def _review_repo(make_repo):
    # clean base repo (README, LICENSE, pinned requirements) + only "needs review" problems
    return make_repo({"run.py": 'import json\njson.load(open("/Users/x/a.json"))\njson.load(open("gone.json"))\n'})


def test_needs_review_findings_are_tagged_and_separate(make_repo, capsys):
    root = _review_repo(make_repo)
    main(["scan", str(root), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    by_check = {f["check"]: f["needs_review"] for f in data["findings"]}
    assert by_check["PATH001"] is True and by_check["DATA001"] is True
    assert all(by_check[c] is False for c in by_check if not CHECKS[c].needs_review)
    assert data["needs_review"]["count"] == sum(by_check.values()) and "about half" in data["needs_review"]["note"]
    # review findings come after the confident ones
    flags = [f["needs_review"] for f in data["findings"]]
    assert flags == sorted(flags)

    main(["scan", str(root)])
    md = capsys.readouterr().out
    assert "## Needs review (" in md and "Check each one against the code before acting" in md
    assert "⚠️ needs review" in md
    review_part = md.split("## Needs review")[1]
    assert "PATH001" in review_part and "DATA001" in review_part
    if "## All findings" in md:
        assert md.index("## All findings") < md.index("## Needs review")
        assert "PATH001" not in md.split("## All findings")[1].split("## Needs review")[0]

    main(["scan", str(root), "-q", "--github-annotations"])
    ann = [l for l in capsys.readouterr().out.splitlines() if "PATH001" in l]
    assert ann and all(l.startswith("::notice ") and "[needs review]" in l and "Needs review" in l for l in ann)


def test_needs_review_findings_never_change_the_grade(make_repo, capsys):
    root = _review_repo(make_repo)
    main(["scan", str(root), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert {f["check"] for f in data["findings"]} >= {"PATH001", "DATA001"}
    assert data["score"]["debt"] == 0 and data["score"]["grade"] == "A"
    assert data["top_fixes"] == [] and data["counts"] == {"high": 0, "medium": 0, "low": 0}
    assert main(["scan", str(root), "-q", "--fail-above", "0"]) == 0
    fs = [Finding("PATH001", "x"), Finding("DATA001", "y"), Finding("DOC003", "z")]
    assert score(fs)["by_check"] == {"DOC003": 4}


def test_confident_only_hides_needs_review(make_repo, capsys):
    root = _review_repo(make_repo)
    main(["scan", str(root), "--format", "json", "--confident-only"])
    data = json.loads(capsys.readouterr().out)
    assert not any(f["needs_review"] for f in data["findings"]) and data["needs_review"]["count"] == 0
    main(["scan", str(root), "--confident-only"])
    md = capsys.readouterr().out
    assert "## Needs review" not in md and "--confident-only" in md


def test_checks_command_lists_precision_and_tags(capsys):
    assert main(["checks"]) == 0
    out = capsys.readouterr().out
    for c in CHECKS.values():
        line = next(l for l in out.splitlines() if l.startswith(c.id + " "))
        assert ("[needs review]" in line) == c.needs_review
        assert "%" in line or "not sampled" in line


def test_confident_only_does_not_leak_into_steps(make_repo, tmp_path, capsys):
    # WF001 (needs review) links model.py to clean.py; DATA001/PATH001 also only need review
    root = make_repo({"requirements.txt": "pandas==2.0\n", "raw.csv": "a\n1\n",
                      "clean.py": 'import pandas as pd\npd.read_csv("raw.csv").to_csv("clean.csv")\n',
                      "model.py": 'import pandas as pd\ndf = pd.read_csv("clean.csv")\nm = pd.read_csv("gone.csv")\n'
                                  'open("/Users/x/a.csv")\n'})
    js = tmp_path / "r.json"
    main(["scan", str(root), "--confident-only", "--json", str(js), "--github-annotations"])
    out = capsys.readouterr().out
    data = json.loads(js.read_text())
    assert all(s["upstream"] == [] and s["status"] == "runnable" and s["reasons"] == [] for s in data["steps"])
    assert "needs review" not in out.lower() and "needs output of" not in out
    for cid in ("WF001", "DATA001", "PATH001"):
        assert cid not in out and cid not in js.read_text()
    # without the flag the same links are shown, tagged
    main(["scan", str(root), "--format", "json"])
    steps = {s["file"]: s for s in json.loads(capsys.readouterr().out)["steps"]}
    assert steps["model.py"]["upstream"] == ["clean.py"] and steps["model.py"]["status"] == "blocked"
