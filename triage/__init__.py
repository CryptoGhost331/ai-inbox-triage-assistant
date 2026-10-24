"""AI Inbox Triage & Draft Assistant.

Reads emails, labels each one, and writes a draft reply in the owner's tone.
It never sends anything: every draft waits for a human to approve it.
"""

__version__ = "1.0.0"

LABELS = ("urgent", "follow-up", "fyi", "ignore")
