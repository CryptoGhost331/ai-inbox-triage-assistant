"""Plain data classes passed between pipeline steps."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from email.utils import parseaddr


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    date: str = ""
    to: str = ""
    list_unsubscribe: str = ""

    @property
    def sender_address(self) -> str:
        return parseaddr(self.sender)[1].lower()

    @property
    def sender_name(self) -> str:
        name = parseaddr(self.sender)[0].strip()
        return name


@dataclass
class TriageResult:
    email_id: str
    sender: str
    subject: str
    label: str
    reason: str
    summary: str = ""
    draft: str = ""
    status: str = "awaiting_approval"  # awaiting_approval | no_reply_needed | skipped | error
    provider: str = "demo"
    error: str = ""
    extras: dict = field(default_factory=dict)

    def to_row(self) -> dict:
        row = asdict(self)
        row.pop("extras")
        return row
