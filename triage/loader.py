"""Load emails from a JSON file or a folder of .eml files (e.g. exported from Gmail)."""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

from .models import Email


def load_emails(path: str | Path) -> list[Email]:
    path = Path(path)
    if path.is_dir():
        return [_load_eml(p) for p in sorted(path.glob("*.eml"))]
    if path.suffix.lower() == ".eml":
        return [_load_eml(path)]
    return _load_json(path)


def _load_json(path: Path) -> list[Email]:
    data = json.loads(path.read_text(encoding="utf-8"))
    emails = []
    for i, item in enumerate(data):
        emails.append(
            Email(
                id=str(item.get("id") or f"msg-{i + 1:03d}"),
                sender=item.get("from", ""),
                to=item.get("to", ""),
                subject=item.get("subject", ""),
                date=item.get("date", ""),
                body=item.get("body", ""),
                list_unsubscribe=item.get("list_unsubscribe", ""),
            )
        )
    return emails


def _load_eml(path: Path) -> Email:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    part = msg.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part is not None else ""
    return Email(
        id=str(msg.get("Message-ID") or path.stem),
        sender=str(msg.get("From", "")),
        to=str(msg.get("To", "")),
        subject=str(msg.get("Subject", "")),
        date=str(msg.get("Date", "")),
        body=body,
        list_unsubscribe=str(msg.get("List-Unsubscribe", "") or ""),
    )
