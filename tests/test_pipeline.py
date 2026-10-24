import csv
import tempfile
import unittest
from pathlib import Path

import triage.pipeline as pipeline_module
from triage.actionlog import ActionLog
from triage.export import write_approval_queue, write_csv
from triage.loader import load_emails
from triage.pipeline import run_pipeline
from triage.providers import DemoProvider
from triage.retry import TransientError

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "data" / "sample_emails.json"


class FlakyProvider:
    """Fails with a transient error a set number of times, then succeeds."""

    name = "flaky"

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def analyze(self, email, text, style_guide):
        self.calls += 1
        if self.calls <= self.failures:
            raise TransientError("HTTP 529: overloaded")
        return {"label": "follow-up", "reason": "r", "summary": "s",
                "needs_reply": True, "draft": "Hi,\n\nOk.\n\nThanks,\nJordan"}


class BrokenProvider:
    name = "broken"

    def analyze(self, email, text, style_guide):
        raise ValueError("model returned unknown label 'spam'")


def one_email():
    return [e for e in load_emails(SAMPLES) if e.id == "msg-010"]


class PipelineTests(unittest.TestCase):
    def test_sample_run(self):
        log = ActionLog(None, "test")
        results = run_pipeline(load_emails(SAMPLES), DemoProvider(), "", log)
        by_id = {r.email_id: r for r in results}

        self.assertEqual(len(results), 12)
        self.assertEqual(by_id["msg-003"].status, "skipped")   # newsletter
        self.assertEqual(by_id["msg-005"].status, "skipped")   # no-reply
        self.assertEqual(by_id["msg-009"].status, "skipped")   # promo
        self.assertEqual(by_id["msg-001"].label, "urgent")
        self.assertEqual(by_id["msg-011"].label, "urgent")
        self.assertEqual(by_id["msg-007"].status, "action_needed")
        self.assertEqual(by_id["msg-008"].label, "fyi")
        self.assertEqual(log.entries[-1]["sent"], 0)

    def test_retries_then_succeeds(self):
        provider = FlakyProvider(failures=2)
        log = ActionLog(None, "test")
        results = run_pipeline(one_email(), provider, "", log, sleep=lambda s: None)
        self.assertEqual(results[0].status, "awaiting_approval")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(sum(e["action"] == "retry" for e in log.entries), 2)

    def test_gives_up_and_alerts_after_max_attempts(self):
        provider = FlakyProvider(failures=99)
        log = ActionLog(None, "test")
        results = run_pipeline(one_email(), provider, "", log, retry_attempts=3,
                               sleep=lambda s: None)
        self.assertEqual(results[0].status, "error")
        self.assertEqual(provider.calls, 3)
        self.assertTrue(any(e["action"] == "alert" for e in log.entries))

    def test_bad_model_output_is_not_retried(self):
        log = ActionLog(None, "test")
        results = run_pipeline(one_email(), BrokenProvider(), "", log, sleep=lambda s: None)
        self.assertEqual(results[0].status, "error")
        self.assertEqual(results[0].draft, "")

    def test_no_send_capability_exists(self):
        source = Path(pipeline_module.__file__).parent
        for path in source.glob("*.py"):
            text = path.read_text().lower()
            for forbidden in ("smtplib", "send_message", "messages.send", "sendmail"):
                self.assertNotIn(forbidden, text, f"{forbidden} found in {path.name}")


class ExportTests(unittest.TestCase):
    def test_csv_and_queue(self):
        results = run_pipeline(load_emails(SAMPLES), DemoProvider(), "", ActionLog(None, "t"))
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = write_csv(results, Path(tmp) / "out.csv")
            with open(csv_path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 12)
            self.assertEqual(rows[0]["label"], "urgent")  # sorted urgent first

            queue = write_approval_queue(results, Path(tmp) / "queue.md").read_text()
            self.assertIn("Nothing has been sent", queue)

    def test_action_log_written_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = ActionLog(Path(tmp) / "logs", "t")
            run_pipeline(one_email(), DemoProvider(), "", log)
            lines = (Path(tmp) / "logs" / "actions.jsonl").read_text().splitlines()
            self.assertGreaterEqual(len(lines), 4)


if __name__ == "__main__":
    unittest.main()
