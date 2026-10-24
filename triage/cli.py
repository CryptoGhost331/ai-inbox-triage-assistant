"""Command line entry point: python -m triage"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from .actionlog import ActionLog
from .export import format_table, write_approval_queue, write_csv, write_json
from .loader import load_emails
from .pipeline import run_pipeline
from .providers import choose_provider

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m triage",
        description="Label emails and draft replies in the owner's tone. Never sends anything.",
    )
    p.add_argument("--input", default=str(ROOT / "data" / "sample_emails.json"),
                   help="JSON file, a .eml file, or a folder of .eml files (default: sample emails)")
    p.add_argument("--style-guide", default=str(ROOT / "data" / "style_guide.md"),
                   help="owner's tone and style guide (markdown)")
    p.add_argument("--provider", choices=["auto", "demo", "anthropic", "openai"], default="auto",
                   help="auto uses Claude or OpenAI if an API key is set, else demo mode")
    p.add_argument("--out", default="output", help="folder for results (default: ./output)")
    p.add_argument("--dry-run", action="store_true",
                   help="process and print results, but write no files and no logs")
    p.add_argument("--retries", type=int, default=4, help="attempts per email on transient errors")
    args = p.parse_args(argv)

    emails = load_emails(args.input)
    style_guide = Path(args.style_guide).read_text(encoding="utf-8")
    provider = choose_provider(args.provider)

    run_id = uuid.uuid4().hex[:8]
    out_dir = Path(args.out)
    log = ActionLog(None if args.dry_run else out_dir / "logs", run_id)

    mode = "DEMO (no API key, rule-based)" if provider.name == "demo" else f"LIVE ({provider.name})"
    print(f"Run {run_id} | mode: {mode} | emails: {len(emails)}"
          f"{' | DRY RUN: nothing written' if args.dry_run else ''}\n")

    results = run_pipeline(emails, provider, style_guide, log, retry_attempts=args.retries)

    print(format_table(results))
    drafts = sum(r.status == "awaiting_approval" for r in results)
    errors = sum(r.status == "error" for r in results)
    print(f"\n{drafts} draft(s) held for approval | {errors} error(s) | 0 emails sent")

    if not args.dry_run:
        csv_path = write_csv(results, out_dir / "triage_results.csv")
        json_path = write_json(results, out_dir / "triage_results.json")
        queue_path = write_approval_queue(results, out_dir / "approval_queue.md")
        print(f"\nWrote {csv_path}, {json_path}, {queue_path}")
        print(f"Action log: {out_dir / 'logs' / 'actions.jsonl'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
