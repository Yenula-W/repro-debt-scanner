"""Command line entry point: `repro-debt scan <path>`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from . import __version__
from .checks import run_checks
from .model import CHECKS, CONFIDENT_CHECKS, precision_text
from .repo import load_repo
from .report import build, to_github_annotations, to_json, to_markdown


def scan_path(path: str, exclude: Sequence[str] = (), confident_only: bool = False,
              enabled: Optional[Set[str]] = None) -> Dict:
    """Scan a folder and return the report dict (same as --json).

    All checks run by default; findings from less reliable checks carry "needs_review": true and never count
    toward the grade. `confident_only` drops them; `enabled` limits the check ids reported.
    """
    repo = load_repo(path, exclude)
    if enabled is None:
        enabled = set(CONFIDENT_CHECKS) if confident_only else set(CHECKS)
    elif confident_only:
        enabled = set(enabled) & set(CONFIDENT_CHECKS)
    report = build(run_checks(repo, set(enabled)), Path(path).resolve().name)
    report["confident_only"] = confident_only
    return report


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles cannot print every character
        stream.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(prog="repro-debt", description="Scan research code for reproducibility debt.")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="scan a repository directory")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--format", choices=["md", "json", "both"], default="md",
                   help="what to print to stdout (default: md)")
    s.add_argument("--md", metavar="FILE", help="also write the Markdown report to FILE")
    s.add_argument("--json", metavar="FILE", help="also write the JSON report to FILE")
    s.add_argument("--github-annotations", action="store_true",
                   help="print GitHub Actions ::error/::warning annotations")
    s.add_argument("--annotation-prefix", default=None, metavar="DIR",
                   help="prefix for annotation file paths (default: the scanned path)")
    s.add_argument("--fail-above", type=int, default=None, metavar="N",
                   help="exit with status 1 if the debt score is above N")
    s.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip files/dirs matching GLOB, relative to the scanned path (repeatable)")
    s.add_argument("--confident-only", action="store_true",
                   help='hide findings from checks marked "needs review" (see `repro-debt checks`)')
    s.add_argument("--quiet", "-q", action="store_true", help="print nothing to stdout")
    sub.add_parser("checks", help="list all checks")
    args = ap.parse_args(argv)

    if args.cmd == "checks":
        print(f"{'ID':8} {'SEVERITY':8} {'CATEGORY':11} {'PRECISION*':13} CHECK")
        for c in CHECKS.values():
            tag = "[needs review] " if c.needs_review else ""
            print(f"{c.id:8} {c.severity:8} {c.category:11} {precision_text(c.id):13} {tag}{c.title}")
        print("\n* untouched hand-checked precision on 75 held-out repos (EVALUATION.md section 7).\n"
              "  [needs review] findings are reported separately and never count toward the grade;\n"
              "  hide them with --confident-only.")
        return 0
    if args.cmd != "scan":
        ap.print_help()
        return 2
    if not Path(args.path).is_dir():
        print(f"error: {args.path} is not a directory", file=sys.stderr)
        return 2

    report = scan_path(args.path, args.exclude, confident_only=args.confident_only)
    md, js = to_markdown(report), to_json(report)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(js, encoding="utf-8")
    if not args.quiet:
        if args.format in ("md", "both"):
            print(md)
        if args.format in ("json", "both"):
            print(js)
    if args.github_annotations:
        prefix = args.annotation_prefix if args.annotation_prefix is not None else args.path
        print(to_github_annotations(report, "" if Path(prefix).is_absolute() else prefix))
    if args.fail_above is not None and report["score"]["debt"] > args.fail_above:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
