#!/usr/bin/env python3
"""collect-logs.py -- LAB log triage helper (standard library only).

Two input modes (pick exactly one):
  --dir PATH        read every ``*.log`` file in a directory
  --container NAME  run ``docker logs`` against a container (needs a Docker host)

It summarizes what it finds -- totals, error/warning counts, the most
frequent error lines, a per-file breakdown, and the observed time range --
then prints a plain-text report (optionally also saved with --output).

Examples:
  python3 scripts/collect-logs.py --dir /tmp/logs --top 20
  python3 scripts/collect-logs.py --dir /tmp/logs --output report.txt
  python3 scripts/collect-logs.py --container lab-app --tail 500
"""
import argparse
import collections
import datetime
import os
import re
import shutil
import subprocess
import sys

# A line counts as an *error* if any of these appears as a whole word.
# Deliberately heuristic: log triage, not log parsing.
ERROR_RE = re.compile(
    r"\b(error|err|crit(ical)?|fatal|exception|traceback|failed|failure|panic)\b",
    re.IGNORECASE,
)
WARN_RE = re.compile(r"\b(warn(ing)?)\b", re.IGNORECASE)
# Loose timestamp matcher for the "observed range" line, e.g.
# 2026-10-20 08:01:11 or 2026-10-20T08:01:11. Not a full parser on purpose.
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")

DEFAULT_TAIL = 200
DEFAULT_TOP = 10


def iter_log_files(log_dir):
    """Yield sorted ``*.log`` file paths inside *log_dir*."""
    return sorted(
        os.path.join(log_dir, name)
        for name in os.listdir(log_dir)
        if name.endswith(".log") and os.path.isfile(os.path.join(log_dir, name))
    )


def read_entries(log_dir):
    """Read every ``*.log`` in *log_dir* -> list of (source, lineno, text)."""
    entries = []
    for path in iter_log_files(log_dir):
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for lineno, line in enumerate(fh, 1):
                    entries.append((name, lineno, line.rstrip("\n")))
        except OSError as exc:
            print(f"warning: skipping {name}: {exc}", file=sys.stderr)
    return entries


def docker_log_text(container, tail=DEFAULT_TAIL):
    """Return ``docker logs --tail N <container>`` output as text.

    Raises RuntimeError if the docker CLI is missing or the command fails,
    so callers (and tests) get a clean, catchable error instead of a
    traceback from deep inside subprocess.
    """
    if shutil.which("docker") is None:
        raise RuntimeError(
            "docker CLI not found on PATH -- container mode needs a Docker "
            "host. Use --dir mode with exported log files instead."
        )
    proc = subprocess.run(
        ["docker", "logs", "--tail", str(tail), container],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker logs failed for {container!r}: {proc.stderr.strip()}"
        )
    return proc.stdout


def summarize(entries, top_n=DEFAULT_TOP):
    """Aggregate (source, lineno, text) entries into a summary dict."""
    total = len(entries)
    error_lines = [text for _, _, text in entries if ERROR_RE.search(text)]
    warn_lines = [text for _, _, text in entries if WARN_RE.search(text)]

    per_file = collections.defaultdict(lambda: {"lines": 0, "errors": 0})
    for source, _, text in entries:
        per_file[source]["lines"] += 1
        if ERROR_RE.search(text):
            per_file[source]["errors"] += 1

    top_errors = [
        (count, text)
        for text, count in collections.Counter(
            line.strip() for line in error_lines if line.strip()
        ).most_common(top_n)
    ]

    timestamps = []
    for _, _, text in entries:
        m = TS_RE.search(text)
        if m:
            timestamps.append(f"{m.group(1)} {m.group(2)}")
    timestamps.sort()

    return {
        "total": total,
        "errors": len(error_lines),
        "warnings": len(warn_lines),
        "top_errors": top_errors,
        "per_file": dict(sorted(per_file.items())),
        "first_ts": timestamps[0] if timestamps else None,
        "last_ts": timestamps[-1] if timestamps else None,
    }


def format_report(summary, source_desc, generated_at=None):
    """Render a summary dict as a plain-text report."""
    if generated_at is None:
        generated_at = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    total = summary["total"]
    errors = summary["errors"]
    err_pct = (errors / total * 100) if total else 0.0

    lines = [
        "LOG COLLECTION REPORT (LAB)",
        f"Source       : {source_desc}",
        f"Generated    : {generated_at}",
        "",
        f"Total lines  : {total}",
        f"Error lines  : {errors} ({err_pct:.1f}%)",
        f"Warning lines: {summary['warnings']}",
    ]
    if summary["first_ts"]:
        lines.append(f"Time range   : {summary['first_ts']} -> {summary['last_ts']}")
    else:
        lines.append("Time range   : n/a (no timestamps detected)")
    lines.append("")
    lines.append(f"Top {len(summary['top_errors'])} error lines (by frequency):")
    if summary["top_errors"]:
        width = len(str(summary["top_errors"][0][0]))
        for count, text in summary["top_errors"]:
            lines.append(f"  {count:>{width}}x  {text[:160]}")
    else:
        lines.append("  (none)")
    lines.append("")
    lines.append("Per-file breakdown:")
    if summary["per_file"]:
        for name, stats in summary["per_file"].items():
            lines.append(
                f"  {name}: {stats['lines']} lines, {stats['errors']} errors"
            )
    else:
        lines.append("  (no files)")
    return "\n".join(lines) + "\n"


def build_parser():
    p = argparse.ArgumentParser(
        description="LAB log triage helper (standard library only)."
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--dir", help="directory of *.log files to analyze")
    src.add_argument(
        "--container", help="container name for `docker logs` (needs a Docker host)"
    )
    p.add_argument(
        "--tail", type=int, default=DEFAULT_TAIL,
        help=f"lines for --container mode (default: {DEFAULT_TAIL})",
    )
    p.add_argument(
        "--top", type=int, default=DEFAULT_TOP,
        help=f"how many top error lines to show (default: {DEFAULT_TOP})",
    )
    p.add_argument("--output", help="also write the report to this file")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.dir:
        if not os.path.isdir(args.dir):
            print(f"error: not a directory: {args.dir}", file=sys.stderr)
            return 2
        entries = read_entries(args.dir)
        source_desc = (
            f"directory {args.dir} ({len(iter_log_files(args.dir))} .log file(s))"
        )
    else:
        try:
            text = docker_log_text(args.container, tail=args.tail)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        entries = [
            (args.container, i, line)
            for i, line in enumerate(text.splitlines(), 1)
        ]
        source_desc = f"container {args.container} (docker logs --tail {args.tail})"

    summary = summarize(entries, top_n=args.top)
    report = format_report(summary, source_desc)
    print(report, end="")
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(report)
        except OSError as exc:
            print(f"error: cannot write {args.output}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
