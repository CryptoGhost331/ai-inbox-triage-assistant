"""Labelling and drafting providers.

- DemoProvider: rule-based, runs offline with no API key. Lets anyone try the
  tool in one command and shows the exact output shape.
- AnthropicProvider / OpenAIProvider: send only the trimmed email text plus the
  style guide to the model and ask for structured JSON back.

All providers return the same dict:
    {"label", "reason", "summary", "needs_reply", "draft"}
None of them can send email. There is no send function anywhere in this project.
"""

from __future__ import annotations

import json
import os
import re
import socket
import urllib.error
import urllib.request

from . import LABELS
from .models import Email
from .retry import TransientError

# ---------------------------------------------------------------- demo mode

URGENT_WORDS = (
    "urgent", "asap", "today", "tomorrow", "action required", "running late",
    "won't start", "expire", "deadline", "immediately", "compliance hold",
)
REQUEST_WORDS = (
    "?", "can you", "could you", "please confirm", "let me know", "please advise",
    "would it be ok", "following up", "enquiry", "inquiry",
)
FYI_WORDS = ("thank you", "thanks so much", "reminder", "no rsvp needed", "fyi")

TOPIC_LINES = [
    (("enquiry", "inquiry", "availability", "rates", "looking for"),
     "Thanks for getting in touch, and I'm sorry to hear things have been difficult. I'd be glad "
     "to talk through what's needed. Could we book a short call? I can do [CONFIRM TIMES], and "
     "I'll share availability and rates after that."),
    (("running late", "won't start", "cover"),
     "Thanks for the heads-up. Leave it with me: I'll arrange cover or call the client, "
     "and I'll text you by [CONFIRM TIME]."),
    (("invoice", "billing", "charged", "double-counted", "payment"),
     "Thanks for flagging this. Leave it with me: I'll check the visit records against the "
     "invoice and come back to you by [CONFIRM DAY]."),
    (("swap", "shift", "roster"),
     "Thanks for checking. I'll look at the roster and confirm by [CONFIRM TIME]."),
    (("visit", "appointment", "earlier", "carer"),
     "Thanks for letting me know. I'm checking the roster now and will come back to you by "
     "[CONFIRM TIME] today."),
    (("delivery", "schedule change", "confirm you've received"),
     "Thanks for letting us know. Confirming we've received this. I'll check whether any client "
     "needs a different arrangement and come back to you by [CONFIRM DAY]."),
]
DEFAULT_LINE = "Thanks for your email. Leave it with me and I'll come back to you by [CONFIRM DAY]."


def _has(haystack: str, keyword: str) -> bool:
    """Whole-word match, so 'charged' does not match inside 'discharged'."""
    pattern = re.escape(keyword)
    if keyword[:1].isalnum():
        pattern = r"\b" + pattern
    if keyword[-1:].isalnum():
        pattern = pattern + r"\b"
    return re.search(pattern, haystack) is not None


ORG_WORDS = {
    "pharmacy", "team", "unit", "network", "ltd", "inc", "llc", "services", "support",
    "clinic", "office", "deals", "weekly", "news", "admin", "billing", "group",
}


def _first_name(email: Email) -> str:
    name = email.sender_name
    if not name or any(c in name for c in "@<>") or len(name.split()) > 3:
        return ""
    if any(word.lower() in ORG_WORDS for word in name.split()):
        return ""
    first = name.split()[0]
    return first if first[:1].isupper() and first.isalpha() else ""


class DemoProvider:
    name = "demo"

    def __init__(self, owner_name: str = "Jordan"):
        self.owner_name = owner_name

    def analyze(self, email: Email, text: str, style_guide: str) -> dict:
        haystack = f"{email.subject}\n{text}".lower()
        urgent = [w for w in URGENT_WORDS if _has(haystack, w)]
        requests = [w for w in REQUEST_WORDS if _has(haystack, w)]
        fyi = [w for w in FYI_WORDS if _has(haystack, w)]

        if urgent:
            label, reason = "urgent", f"time-sensitive wording: {', '.join(urgent[:3])}"
        elif requests:
            label, reason = "follow-up", f"asks for a reply: {', '.join(requests[:3])}"
        elif fyi:
            label, reason = "fyi", f"informational: {', '.join(fyi[:2])}"
        else:
            label, reason = "fyi", "no request or deadline found"

        needs_reply = bool(requests)
        summary = _first_sentence(text)
        draft = self._draft(email, haystack) if needs_reply else ""
        return {
            "label": label,
            "reason": reason,
            "summary": summary,
            "needs_reply": needs_reply,
            "draft": draft,
        }

    def _draft(self, email: Email, haystack: str) -> str:
        line = DEFAULT_LINE
        for keywords, topic_line in TOPIC_LINES:
            if any(_has(haystack, k) for k in keywords):
                line = topic_line
                break
        first = _first_name(email)
        greeting = f"Hi {first}," if first else "Hello,"
        return f"{greeting}\n\n{line}\n\nThanks,\n{self.owner_name}"


def _first_sentence(text: str, limit: int = 160) -> str:
    flat = " ".join(
        line.strip() for line in text.splitlines()
        if line.strip() and not re.match(r"^(hi|hello|dear|hey)\b", line.strip(), re.I)
    )
    sentences = re.findall(r"[^.!?]+[.!?]", flat) or [flat]
    sentence = next((x.strip() for x in sentences if len(x.split()) >= 6), sentences[0].strip())
    return sentence if len(sentence) <= limit else sentence[: limit - 3].rstrip() + "..."


# ---------------------------------------------------------------- LLM modes

SYSTEM_PROMPT = """You triage email for a small business owner and draft replies in their voice.

Return ONLY a JSON object with these keys:
  "label": one of "urgent", "follow-up", "fyi", "ignore"
  "reason": one short phrase explaining the label
  "summary": one sentence summarising the email
  "needs_reply": true if the sender is asking the owner for something, else false
  "draft": the reply text if needs_reply is true, otherwise ""

Label rules:
- urgent: a deadline, safety issue, or something that must happen today or tomorrow
- follow-up: needs a reply or action, but not today
- fyi: worth knowing, no reply needed
- ignore: marketing, spam, automated notices

Draft rules:
- Follow the owner's style guide exactly.
- Never promise a time, price, or staff change. Use placeholders like [CONFIRM TIME].
- Never add personal or health details the sender did not write.
- The draft will be reviewed by the owner before anything is sent.

Owner's style guide:
{style_guide}
"""


def _build_user_message(email: Email, text: str) -> str:
    return f"From: {email.sender}\nSubject: {email.subject}\n\n{text}"


def parse_model_json(raw: str) -> dict:
    """Pull the JSON object out of a model reply and validate it."""
    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    else:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("model reply contained no JSON object")
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    label = str(data.get("label", "")).strip().lower()
    if label not in LABELS:
        raise ValueError(f"model returned unknown label {label!r}")
    needs_reply = bool(data.get("needs_reply"))
    return {
        "label": label,
        "reason": str(data.get("reason", "")).strip(),
        "summary": str(data.get("summary", "")).strip(),
        "needs_reply": needs_reply,
        "draft": str(data.get("draft", "")).strip() if needs_reply else "",
    }


def _post_json(url: str, headers: dict, payload: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 429 or exc.code >= 500:
            raise TransientError(f"HTTP {exc.code}: {detail}") from exc
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
        raise TransientError(str(exc)) from exc


class AnthropicProvider:
    name = "anthropic"
    url = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ["ANTHROPIC_API_KEY"]
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")

    def analyze(self, email: Email, text: str, style_guide: str) -> dict:
        payload = {
            "model": self.model,
            "max_tokens": 800,
            "system": SYSTEM_PROMPT.format(style_guide=style_guide),
            "messages": [{"role": "user", "content": _build_user_message(email, text)}],
        }
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        data = _post_json(self.url, headers, payload)
        raw = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return parse_model_json(raw)


class OpenAIProvider:
    name = "openai"
    url = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ["OPENAI_API_KEY"]
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def analyze(self, email: Email, text: str, style_guide: str) -> dict:
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(style_guide=style_guide)},
                {"role": "user", "content": _build_user_message(email, text)},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = _post_json(self.url, headers, payload)
        raw = data["choices"][0]["message"]["content"]
        return parse_model_json(raw)


def choose_provider(requested: str = "auto"):
    """auto = Claude if ANTHROPIC_API_KEY is set, else OpenAI if OPENAI_API_KEY is set, else demo."""
    if requested == "demo":
        return DemoProvider()
    for name, var in (("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")):
        if requested == name and not os.environ.get(var):
            raise SystemExit(f"--provider {name} needs {var} set. Or run without it for demo mode.")
    if requested == "anthropic" or (requested == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        return AnthropicProvider()
    if requested == "openai" or (requested == "auto" and os.environ.get("OPENAI_API_KEY")):
        return OpenAIProvider()
    return DemoProvider()
