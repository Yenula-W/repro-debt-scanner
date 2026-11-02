"""Command line entry point: `repro-debt scan <path>`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .checks import run_checks
from .model import CHECKS
from .repo import load_repo
from .report import build, to_github_annotations, to_json, to_markdown


def scan_path(path: str) -> Dict:
    repo = load_repo(path)
    return build(run_checks(repo), Path(path).resolve().name)


def main(argv: Optional[List[str]] = None) -> int:
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
    s.add_argument("--fail-above", type=int, default=None, metavar="N",
                   help="exit with status 1 if the debt score is above N")
    s.add_argument("--quiet", "-q", action="store_true", help="print nothing to stdout")
    sub.add_parser("checks", help="list all checks")
    args = ap.parse_args(argv)

    if args.cmd == "checks":
        for c in CHECKS.values():
            print(f"{c.id:8} {c.severity:7} {c.category:11} {c.title}")
        return 0
    if args.cmd != "scan":
        ap.print_help()
        return 2
    if not Path(args.path).is_dir():
        print(f"error: {args.path} is not a directory", file=sys.stderr)
        return 2

    report = scan_path(args.path)
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
        print(to_github_annotations(report))
    if args.fail_above is not None and report["score"]["debt"] > args.fail_above:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
