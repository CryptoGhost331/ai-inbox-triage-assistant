"""Write results to CSV (opens directly in Google Sheets / Excel) and an
approval queue the owner reads before anything is sent."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import TriageResult

CSV_COLUMNS = [
    "email_id", "label", "status", "sender", "subject", "reason", "summary",
    "draft", "provider", "error",
]
LABEL_ORDER = {"urgent": 0, "needs-review": 1, "follow-up": 2, "fyi": 3, "ignore": 4}


def sort_results(results: list[TriageResult]) -> list[TriageResult]:
    return sorted(results, key=lambda r: LABEL_ORDER.get(r.label, 9))


def write_csv(results: list[TriageResult], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in sort_results(results):
            writer.writerow(r.to_row())
    return path


def write_json(results: list[TriageResult], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([r.to_row() for r in sort_results(results)], indent=2), encoding="utf-8")
    return path


def write_approval_queue(results: list[TriageResult], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    drafts = [r for r in sort_results(results) if r.status == "awaiting_approval"]
    actions = [r for r in sort_results(results) if r.status in ("action_needed", "error")]

    lines = [
        "# Approval queue",
        "",
        f"{len(drafts)} draft(s) waiting for your review. Nothing has been sent.",
        "",
    ]
    if actions:
        lines += ["## Needs your attention (no draft)", ""]
        for r in actions:
            note = r.error or r.summary or r.reason
            lines.append(f"- **[{r.label.upper()}]** {r.subject} ({r.sender}): {note}")
        lines.append("")
    for i, r in enumerate(drafts, 1):
        lines += [
            f"## {i}. [{r.label.upper()}] {r.subject}",
            "",
            f"**From:** {r.sender}  ",
            f"**Why:** {r.reason}  ",
            f"**Summary:** {r.summary}",
            "",
            "```text",
            r.draft,
            "```",
            "",
            "- [ ] Approve and send   - [ ] Edit first   - [ ] Discard",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def format_table(results: list[TriageResult]) -> str:
    rows = [("LABEL", "STATUS", "FROM", "SUBJECT")]
    for r in sort_results(results):
        sender = r.sender.split("<")[0].strip() or r.sender
        rows.append((r.label, r.status, sender[:24], r.subject[:48]))
    widths = [max(len(row[i]) for row in rows) for i in range(4)]
    return "\n".join("  ".join(cell.ljust(w) for cell, w in zip(row, widths)) for row in rows)
