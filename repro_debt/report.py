"""Scoring and report rendering (Markdown, JSON, GitHub annotations)."""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Dict, List

from . import __version__
from .checks import ScanResult
from .model import CHECKS, PER_CHECK_CAP, SEVERITY_WEIGHT, Finding

SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
GRADES = [(0, "A"), (10, "B"), (25, "C"), (50, "D")]
GRADE_TEXT = {
    "A": "No reproducibility debt found.",
    "B": "Minor debt; a stranger could probably re-run this with a little effort.",
    "C": "Moderate debt; expect to spend hours getting this to run.",
    "D": "Heavy debt; re-running this would likely need help from the authors.",
    "F": "Severe debt; results are very unlikely to be reproducible as-is.",
}


def score(findings: List[Finding]) -> Dict:
    by_check: "OrderedDict[str, List[Finding]]" = OrderedDict()
    for f in findings:
        by_check.setdefault(f.check, []).append(f)
    contrib = {}
    for cid, fs in by_check.items():
        w = SEVERITY_WEIGHT[CHECKS[cid].severity]
        contrib[cid] = w * min(len(fs), PER_CHECK_CAP)
    total = sum(contrib.values())
    grade = "F"
    for limit, g in GRADES:
        if total <= limit:
            grade = g
            break
    return {"debt": total, "grade": grade, "summary": GRADE_TEXT[grade], "by_check": contrib}


def top_fixes(findings: List[Finding], contrib: Dict[str, int], n: int = 5) -> List[Dict]:
    ranked = sorted(contrib, key=lambda c: (-contrib[c], SEV_ORDER[CHECKS[c].severity], c))
    out = []
    for cid in ranked[:n]:
        fs = [f for f in findings if f.check == cid]
        details = list(OrderedDict.fromkeys(f.detail or f.location for f in fs))
        ex = ", ".join(f"`{d}`" for d in details[:4]) + (f" and {len(details) - 4} more" if len(details) > 4 else "")
        out.append({
            "check": cid,
            "title": CHECKS[cid].title,
            "severity": CHECKS[cid].severity,
            "count": len(fs),
            "points": contrib[cid],
            "fix": CHECKS[cid].fix.format(examples=ex or "see below"),
        })
    return out


def build(result: ScanResult, target: str) -> Dict:
    findings = sorted(result.findings, key=lambda f: (SEV_ORDER[f.severity], f.check, f.file or "", f.line or 0))
    sc = score(findings)
    steps = result.steps
    runnable = sum(1 for s in steps if s.status == "runnable")
    return {
        "tool": "repro-debt-scanner",
        "version": __version__,
        "target": target,
        "score": sc,
        "top_fixes": top_fixes(findings, sc["by_check"]),
        "counts": {sev: sum(1 for f in findings if f.severity == sev) for sev in ("high", "medium", "low")},
        "stats": {
            "python_files": sum(1 for u in result.repo.units if u.lang == "python" and not u.is_notebook),
            "notebooks": sum(1 for u in result.repo.units if u.is_notebook),
            "r_files": sum(1 for u in result.repo.units if u.lang == "r" and not u.is_notebook),
            "dependency_files": [d.file for d in result.repo.deps],
            "steps": len(steps),
            "steps_runnable": runnable,
        },
        "steps": [s.to_dict() for s in steps],
        "findings": [f.to_dict() for f in findings],
    }


def to_json(report: Dict) -> str:
    return json.dumps(report, indent=2)


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def to_markdown(report: Dict, max_findings: int = 200) -> str:
    sc = report["score"]
    st = report["stats"]
    L = []
    L.append(f"# Reproducibility debt report: `{report['target']}`\n")
    L.append(f"**Debt score: {sc['debt']} points — grade {sc['grade']}.** {sc['summary']}\n")
    c = report["counts"]
    L.append(f"{c['high']} high, {c['medium']} medium, {c['low']} low severity issues · "
             f"{st['python_files']} Python files, {st['notebooks']} notebooks, {st['r_files']} R files · "
             f"dependency files: {', '.join(st['dependency_files']) or 'none'}\n")
    L.append("_Lower is better. Each issue type adds points by severity (high 10, medium 4, low 1), "
             f"counted at most {PER_CHECK_CAP} times._\n")

    if report["top_fixes"]:
        L.append("## Top fixes\n")
        for i, t in enumerate(report["top_fixes"], 1):
            L.append(f"{i}. **{t['title']}** ({t['severity']}, {t['count']} found, {t['points']} pts) — {t['fix']}")
        L.append("")

    steps = report["steps"]
    if steps:
        L.append("## Can each step be re-run?\n")
        L.append(f"{st['steps_runnable']} of {st['steps']} scripts/notebooks have no detected blockers.\n")
        L.append("| Step | Status | Likely cause if it breaks | Why |")
        L.append("|---|---|---|---|")
        order = {"blocked": 0, "needs-upstream": 1, "runnable": 2}
        for s in sorted(steps, key=lambda s: (order[s["status"]], s["file"]))[:60]:
            why = "; ".join(s["reasons"][:3]) + (f" (+{len(s['reasons']) - 3} more)" if len(s["reasons"]) > 3 else "")
            if s["upstream"]:
                why = (why + "; " if why else "") + "needs output of " + ", ".join(f"`{u}`" for u in s["upstream"][:3])
            status = {"blocked": "❌ blocked", "needs-upstream": "⏳ needs earlier step", "runnable": "✅ runnable"}[s["status"]]
            L.append(f"| `{s['file']}` | {status} | {s['likely_break'] or '—'} | {_esc(why) or '—'} |")
        if len(steps) > 60:
            L.append(f"\n_…and {len(steps) - 60} more steps (see JSON report)._")
        L.append("")

    fs = report["findings"]
    if fs:
        L.append("## All findings\n")
        L.append("| Severity | Check | Where | What |")
        L.append("|---|---|---|---|")
        for f in fs[:max_findings]:
            L.append(f"| {f['severity']} | {f['check']} {f['title']} | `{_esc(f['location'])}` | {_esc(f['message'])} |")
        if len(fs) > max_findings:
            L.append(f"\n_…and {len(fs) - max_findings} more (see JSON report)._")
        L.append("")
    else:
        L.append("No issues found. 🎉\n")
    L.append(f"<sub>Generated by repro-debt-scanner {report['version']}. Static analysis only: it does not run "
             "your code, so treat findings as leads, not verdicts.</sub>")
    return "\n".join(L) + "\n"


def to_github_annotations(report: Dict, prefix: str = "") -> str:
    prefix = prefix.strip().rstrip("/")
    prefix = "" if prefix in ("", ".") else re.sub(r"^(\./)+", "", prefix) + "/"
    out = []
    for f in report["findings"]:
        level = {"high": "error", "medium": "warning", "low": "notice"}[f["severity"]]
        props = []
        if f["file"]:
            props.append(f"file={prefix}{f['file']}")
            if f["line"] and f["cell"] is None:
                props.append(f"line={f['line']}")
        props.append(f"title={f['check']} {f['title']}")
        msg = f["message"].replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        out.append(f"::{level} {','.join(p.replace(',', '%2C').replace('::', '%3A%3A') for p in props)}::{msg}")
    return "\n".join(out)
