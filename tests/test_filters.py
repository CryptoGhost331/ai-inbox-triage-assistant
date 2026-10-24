import unittest

from triage.filters import skip_reason, trim_body
from triage.models import Email


def make(sender="Ann Lee <ann@example.com>", body="Hi", **kw):
    return Email(id="t", sender=sender, subject=kw.pop("subject", "Hello"), body=body, **kw)


class SkipReasonTests(unittest.TestCase):
    def test_no_reply_sender_is_skipped(self):
        self.assertIn("no-reply", skip_reason(make(sender="no-reply@bank.example")))

    def test_list_unsubscribe_header_is_skipped(self):
        self.assertIsNotNone(skip_reason(make(list_unsubscribe="<https://x.example/u>")))

    def test_unsubscribe_footer_is_skipped(self):
        self.assertIsNotNone(skip_reason(make(body="Big sale!\n\nUnsubscribe here")))

    def test_real_person_is_kept(self):
        self.assertIsNone(skip_reason(make(body="Can you call me back today?")))


class TrimBodyTests(unittest.TestCase):
    def test_drops_quoted_history(self):
        body = "Thanks, that works.\n\nOn Fri, Oct 17, 2026 at 4:12 PM Ann wrote:\n> old text"
        self.assertEqual(trim_body(body), "Thanks, that works.")

    def test_drops_signature(self):
        body = "See you Tuesday.\n\n--\nAnn Lee\nMobile: 555-0100"
        self.assertEqual(trim_body(body), "See you Tuesday.")

    def test_drops_sent_from_iphone(self):
        self.assertEqual(trim_body("On my way.\n\nSent from my iPhone"), "On my way.")

    def test_caps_length(self):
        out = trim_body("word " * 1000, max_chars=100)
        self.assertLessEqual(len(out), 110)
        self.assertTrue(out.endswith("[...]"))


if __name__ == "__main__":
    unittest.main()
