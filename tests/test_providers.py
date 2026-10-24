import unittest
from unittest import mock

import triage.providers as providers

from triage.models import Email
from triage.providers import DemoProvider, parse_model_json


def make(sender, subject, body):
    return Email(id="t", sender=sender, subject=subject, body=body)


class DemoProviderTests(unittest.TestCase):
    def setUp(self):
        self.p = DemoProvider(owner_name="Jordan")

    def analyze(self, sender, subject, body):
        return self.p.analyze(make(sender, subject, body), body, "")

    def test_deadline_is_urgent(self):
        out = self.analyze("Ann Lee <ann@x.example>", "Visit", "Can you come earlier tomorrow?")
        self.assertEqual(out["label"], "urgent")
        self.assertTrue(out["draft"].startswith("Hi Ann,"))
        self.assertTrue(out["draft"].endswith("Jordan"))

    def test_question_is_follow_up_with_draft(self):
        out = self.analyze("Tom Wu <tom@x.example>", "Invoice", "Could you check the invoice?")
        self.assertEqual(out["label"], "follow-up")
        self.assertIn("invoice", out["draft"])

    def test_thank_you_is_fyi_without_draft(self):
        out = self.analyze("Linda <l@x.example>", "Thank you", "Thank you for everything.")
        self.assertEqual(out["label"], "fyi")
        self.assertEqual(out["draft"], "")

    def test_whole_word_matching(self):
        # 'discharged' must not trigger the billing reply ('charged')
        out = self.analyze("Dan O <d@x.example>", "Enquiry",
                           "Dad was discharged last week. Do you have availability?")
        self.assertIn("call", out["draft"])
        self.assertNotIn("invoice", out["draft"])

    def test_organisation_sender_gets_generic_greeting(self):
        out = self.analyze("Northside Pharmacy <o@x.example>", "Change", "Please confirm receipt.")
        self.assertTrue(out["draft"].startswith("Hello,"))

    def test_drafts_never_promise_times(self):
        out = self.analyze("Ann Lee <ann@x.example>", "Visit", "Can someone come earlier today?")
        self.assertIn("[CONFIRM", out["draft"])


class LiveProviderTests(unittest.TestCase):
    """Live providers with the HTTP call stubbed out: checks request shape and parsing."""

    def test_anthropic_request_and_parse(self):
        reply = {"content": [{"type": "text", "text": '{"label":"follow-up","reason":"asks",'
                              '"summary":"s","needs_reply":true,"draft":"Hi Tom,"}'}]}
        with mock.patch.object(providers, "_post_json", return_value=reply) as post:
            p = providers.AnthropicProvider(api_key="test-key", model="test-model")
            out = p.analyze(make("Tom <t@x.example>", "Invoice", "Could you check?"),
                            "Could you check?", "STYLE")
        url, headers, payload = post.call_args.args
        self.assertEqual(url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(headers["x-api-key"], "test-key")
        self.assertIn("STYLE", payload["system"])
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(out["draft"], "Hi Tom,")

    def test_openai_request_and_parse(self):
        reply = {"choices": [{"message": {"content": '{"label":"ignore","needs_reply":false}'}}]}
        with mock.patch.object(providers, "_post_json", return_value=reply) as post:
            p = providers.OpenAIProvider(api_key="k", model="m")
            out = p.analyze(make("A <a@x.example>", "Hi", "x"), "x", "STYLE")
        self.assertEqual(post.call_args.args[2]["response_format"], {"type": "json_object"})
        self.assertEqual(out["label"], "ignore")

    def test_missing_key_gives_clear_message(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                providers.choose_provider("anthropic")
            self.assertEqual(providers.choose_provider("auto").name, "demo")


class ParseModelJsonTests(unittest.TestCase):
    def test_plain_json(self):
        out = parse_model_json('{"label":"urgent","reason":"r","summary":"s",'
                               '"needs_reply":true,"draft":"Hi"}')
        self.assertEqual(out["label"], "urgent")
        self.assertEqual(out["draft"], "Hi")

    def test_fenced_json(self):
        raw = 'Here you go:\n```json\n{"label":"FYI","needs_reply":false,"draft":"x"}\n```'
        out = parse_model_json(raw)
        self.assertEqual(out["label"], "fyi")
        self.assertEqual(out["draft"], "")  # no draft when no reply is needed

    def test_unknown_label_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_json('{"label":"spam"}')

    def test_no_json_rejected(self):
        with self.assertRaises(ValueError):
            parse_model_json("sorry, I can't help")


if __name__ == "__main__":
    unittest.main()
