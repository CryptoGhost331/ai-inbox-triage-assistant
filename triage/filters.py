"""Cheap, local steps that run before any AI call.

1. Skip newsletters, promotions and no-reply senders (no AI cost, no data sent).
2. Trim what is left to the text a reply actually needs: drop quoted history,
   signatures and phone footers. Less text out means less cost and less
   personal data leaving the inbox.
"""

from __future__ import annotations

import re

from .models import Email

NO_REPLY_PATTERNS = (
    "no-reply",
    "noreply",
    "do-not-reply",
    "donotreply",
    "mailer-daemon",
    "notifications@",
)
BULK_PATTERNS = ("newsletter@", "deals@", "marketing@", "promo@", "news@")
BULK_PHRASES = ("unsubscribe", "manage preferences", "you are receiving this because")

_QUOTE_HEADER = re.compile(r"^On .+wrote:\s*$", re.IGNORECASE)
_SIGNATURE_MARKERS = re.compile(
    r"^(--\s*|__+|sent from my (iphone|ipad|android|phone).*|get outlook for .*)$",
    re.IGNORECASE,
)
MAX_CHARS = 2000


def skip_reason(email: Email) -> str | None:
    """Return why an email should skip the AI step, or None to keep it."""
    addr = email.sender_address
    if any(p in addr for p in NO_REPLY_PATTERNS):
        return "automated no-reply sender"
    if email.list_unsubscribe:
        return "bulk mail (has List-Unsubscribe header)"
    if any(p in addr for p in BULK_PATTERNS):
        return "bulk mail sender"
    lowered = email.body.lower()
    if any(phrase in lowered for phrase in BULK_PHRASES):
        return "bulk mail (unsubscribe footer)"
    return None


def trim_body(body: str, max_chars: int = MAX_CHARS) -> str:
    """Keep only the newest message text: no quoted history, no signature."""
    kept: list[str] = []
    for line in body.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if _QUOTE_HEADER.match(stripped) or _SIGNATURE_MARKERS.match(stripped):
            break
        if stripped.startswith(">"):
            continue
        kept.append(line.rstrip())
    text = "\n".join(kept).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " [...]"
    return text
