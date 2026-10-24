"""Append-only JSON Lines log of every action, plus an alerts file.

Every email produces at least one log line, so you can always answer
"what happened to that message?". Failures also go to alerts.log and stderr,
so nothing fails silently.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class ActionLog:
    def __init__(self, log_dir: str | Path | None, run_id: str):
        self.run_id = run_id
        self.log_dir = Path(log_dir) if log_dir else None
        self.entries: list[dict] = []
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, **details) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "run_id": self.run_id,
            "action": action,
            **details,
        }
        self.entries.append(entry)
        if self.log_dir:
            with open(self.log_dir / "actions.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def alert(self, message: str, **details) -> None:
        self.record("alert", message=message, **details)
        print(f"ALERT: {message}", file=sys.stderr)
        if self.log_dir:
            with open(self.log_dir / "alerts.log", "a", encoding="utf-8") as f:
                f.write(f"{self.run_id} {message} {json.dumps(details)}\n")
