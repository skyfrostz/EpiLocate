#!/usr/bin/env python3
"""Check that engineering changes update both EpiLocate project documents.

The checker deliberately verifies only change scope and document presence. It
does not invent a journal entry, a problem description, a test result, or an
historical explanation.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY = "docs/project/ITERATION_HISTORY.md"
JOURNAL = "docs/project/ENGINEERING_JOURNAL.md"
CHECKER = "scripts/check_project_documentation.py"


def run_git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return [line for line in result.stdout.splitlines() if line]


def diff_paths(spec: str) -> set[str]:
    return set(run_git("diff", "--name-only", "--diff-filter=ACMRTUXB", spec))


def changed_paths(args: argparse.Namespace) -> set[str]:
    if args.base and args.range:
        raise ValueError("--base and --range are mutually exclusive")
    if not args.base and not args.range:
        raise ValueError("one of --base or --range is required")

    if args.base:
        paths = diff_paths(f"{args.base}...HEAD")
    else:
        paths = diff_paths(args.range)

    if args.working_tree:
        paths.update(run_git("diff", "--name-only", "--diff-filter=ACMRTUXB"))
        paths.update(
            run_git("diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB")
        )
        paths.update(run_git("ls-files", "--others", "--exclude-standard"))
    return paths


def is_documentation_only(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized in {"AGENTS.md", CHECKER}:
        return True
    if normalized.startswith("docs/"):
        return True
    if normalized.lower().endswith((".md", ".mdx", ".rst", ".txt")):
        return True
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Require both project history and engineering journal for code changes."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--base",
        help="Git ref to compare with HEAD, using a three-dot diff (for example p0/integration).",
    )
    source.add_argument(
        "--range",
        dest="range",
        help="Git diff range (for example BASE..HEAD or BASE...HEAD).",
    )
    parser.add_argument(
        "--working-tree",
        action="store_true",
        help="Also include staged, unstaged, and untracked working-tree paths.",
    )
    parser.add_argument(
        "--historical-note",
        help="Optional source note printed for a documentation-only historical backfill.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = changed_paths(args)
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not paths:
        print("PASS: no changed paths in the requested scope")
        return 0

    engineering = sorted(path for path in paths if not is_documentation_only(path))
    history_changed = HISTORY in paths
    journal_changed = JOURNAL in paths

    print("Changed paths:")
    for path in sorted(paths):
        print(f"  - {path}")

    if not engineering:
        print("Classification: documentation-only or historical-backfill")
        if args.historical_note:
            print(f"Historical source note: {args.historical_note}")
        print("PASS: no code, test, configuration, or deployment change requires both logs")
        return 0

    print("Classification: engineering-change")
    print("Engineering paths:")
    for path in engineering:
        print(f"  - {path}")

    missing = []
    if not history_changed:
        missing.append(HISTORY)
    if not journal_changed:
        missing.append(JOURNAL)
    if missing:
        print("FAIL: engineering changes must update both project documents:")
        for path in missing:
            print(f"  - {path}")
        return 1

    print(f"PASS: engineering changes include {HISTORY} and {JOURNAL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
