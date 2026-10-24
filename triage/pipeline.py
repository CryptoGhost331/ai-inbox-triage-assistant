"""The triage pipeline: filter -> trim -> label & draft -> hold for approval.

Error path: if any step fails for an email, that email is left untouched,
the failure is logged and alerted, and the run carries on with the next one.
"""

from __future__ import annotations

from .actionlog import ActionLog
from .filters import skip_reason, trim_body
from .models import Email, TriageResult
from .retry import TransientError, with_retries


def run_pipeline(
    emails: list[Email],
    provider,
    style_guide: str,
    log: ActionLog,
    retry_attempts: int = 4,
    retry_base_delay: float = 1.0,
    sleep=None,
) -> list[TriageResult]:
    results: list[TriageResult] = []
    log.record("run_started", provider=provider.name, emails=len(emails))

    retry_kwargs = {"attempts": retry_attempts, "base_delay": retry_base_delay}
    if sleep is not None:
        retry_kwargs["sleep"] = sleep

    def on_retry(attempt, exc, delay):
        log.record("retry", attempt=attempt, wait_seconds=round(delay, 2), error=str(exc)[:200])

    analyze = with_retries(on_retry=on_retry, **retry_kwargs)(provider.analyze)

    for email in emails:
        reason = skip_reason(email)
        if reason:
            results.append(
                TriageResult(
                    email_id=email.id, sender=email.sender, subject=email.subject,
                    label="ignore", reason=reason, status="skipped", provider="filter",
                )
            )
            log.record("skipped", email_id=email.id, reason=reason)
            continue

        text = trim_body(email.body)
        log.record("trimmed", email_id=email.id, chars_in=len(email.body), chars_out=len(text))

        try:
            out = analyze(email, text, style_guide)
        except (TransientError, RuntimeError, ValueError, KeyError) as exc:
            results.append(
                TriageResult(
                    email_id=email.id, sender=email.sender, subject=email.subject,
                    label="needs-review", reason="AI step failed; email left untouched",
                    status="error", provider=provider.name, error=str(exc)[:300],
                )
            )
            log.alert("triage failed", email_id=email.id, error=str(exc)[:300])
            continue

        if out["draft"]:
            status = "awaiting_approval"
        elif out["label"] == "urgent":
            status = "action_needed"
        else:
            status = "no_reply_needed"

        result = TriageResult(
            email_id=email.id, sender=email.sender, subject=email.subject,
            label=out["label"], reason=out["reason"], summary=out["summary"],
            draft=out["draft"], status=status, provider=provider.name,
        )
        results.append(result)
        log.record("labelled", email_id=email.id, label=result.label, status=status)
        if result.draft:
            log.record("draft_held_for_approval", email_id=email.id)

    counts = {}
    for r in results:
        counts[r.label] = counts.get(r.label, 0) + 1
    log.record("run_finished", counts=counts, sent=0)
    return results
