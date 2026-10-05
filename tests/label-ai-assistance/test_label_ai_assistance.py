#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "label_ai_assistance.py"
spec = importlib.util.spec_from_file_location("label_ai_assistance", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LabelAiAssistanceTests(unittest.TestCase):
    def test_body_checkbox_beats_agent(self):
        r = mod.decide(
            {
                "body": "- [x] `ai-reviewed`\n",
                "commits": [],
                "pr_user": "Copilot",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "body-marker")
        self.assertIn("ai-reviewed", r["labels_add"])

    def test_copilot_agent_author(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [],
                "pr_user": "Copilot",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "copilot-cloud-agent")
        self.assertIn("ai-authored", r["labels_add"])
        self.assertIn("ai-label:auto", r["labels_add"])

    def test_trailer_fallback(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [
                    {"sha": "111", "message": "wip\n\nAi-Assisted: authored\n"}
                ],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "commit-trailer")

    def test_slash_override(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [],
                "pr_user": "Copilot",
                "current_labels": [],
                "comments": [{"body": "/ai-label none"}],
            }
        )
        self.assertEqual(r["signal"], "slash-none")
        self.assertIn("ai-label:manual", r["labels_add"])

    def test_manual_lock_noop(self):
        r = mod.decide(
            {
                "body": "- [x] ai-authored\n",
                "commits": [],
                "pr_user": "alice",
                "current_labels": ["ai-label:manual", "ai-declaration:none"],
                "comments": [],
            }
        )
        self.assertEqual(r["action"], "noop")

    def test_remind_when_ready(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [{"sha": "a", "message": "x"}],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
                "ready_for_review": True,
            }
        )
        self.assertEqual(r["action"], "remind")

    def test_dependabot_ignored(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [
                    {
                        "sha": "a",
                        "message": "bump\n\nCo-Authored-By: dependabot[bot] <x@users.noreply.github.com>\n",
                    }
                ],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "none")


if __name__ == "__main__":
    unittest.main()
