#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "label_ai_assistance.py"

spec = importlib.util.spec_from_file_location("label_ai_assistance", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class LabelAiAssistanceTests(unittest.TestCase):
    def test_body_checkbox_beats_cursor(self):
        r = mod.decide(
            {
                "body": "- [x] `ai-reviewed`\n",
                "commits": [{"sha": "abc1234", "message": "x"}],
                "cursor_commits": [
                    {
                        "commitHash": "abc1234ffff",
                        "totalLinesAdded": 100,
                        "tabLinesAdded": 80,
                        "composerLinesAdded": 0,
                    }
                ],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "body-marker")
        self.assertIn("ai-reviewed", r["labels_add"])
        self.assertNotIn("ai-label:auto", r["labels_add"])

    def test_cursor_join_applies_auto(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [{"sha": "deadbeef", "message": "feat"}],
                "cursor_commits": [
                    {
                        "commitHash": "deadbeefcafebabe",
                        "totalLinesAdded": 100,
                        "tabLinesAdded": 5,
                        "composerLinesAdded": 40,
                    }
                ],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "cursor-ai-code-tracking")
        self.assertIn("ai-authored", r["labels_add"])
        self.assertIn("ai-label:auto", r["labels_add"])

    def test_copilot_agent_author(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [],
                "cursor_commits": [],
                "pr_user": "Copilot",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "copilot-cloud-agent")
        self.assertIn("ai-authored", r["labels_add"])

    def test_trailer_fallback_when_no_cursor(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [
                    {"sha": "111", "message": "wip\n\nAi-Assisted: authored\n"}
                ],
                "cursor_commits": [],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "commit-trailer")
        self.assertIn("ai-authored", r["labels_add"])
        self.assertIn("ai-label:auto", r["labels_add"])

    def test_slash_override_sets_manual(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [],
                "cursor_commits": [
                    {
                        "commitHash": "abc",
                        "totalLinesAdded": 50,
                        "composerLinesAdded": 50,
                        "tabLinesAdded": 0,
                    }
                ],
                "commits": [{"sha": "abc", "message": "x"}],
                "pr_user": "alice",
                "current_labels": ["ai-authored", "ai-label:auto"],
                "comments": [{"body": "/ai-label none"}],
            }
        )
        self.assertEqual(r["signal"], "slash-none")
        self.assertIn("ai-declaration:none", r["labels_add"])
        self.assertIn("ai-label:manual", r["labels_add"])
        self.assertTrue(r["manual_lock"])

    def test_manual_lock_noop(self):
        r = mod.decide(
            {
                "body": "- [x] ai-authored\n",
                "commits": [],
                "cursor_commits": [],
                "pr_user": "alice",
                "current_labels": ["ai-label:manual", "ai-declaration:none"],
                "comments": [],
            }
        )
        self.assertEqual(r["action"], "noop")
        self.assertEqual(r["signal"], "manual-lock")

    def test_remind_when_ready_undeclared(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [{"sha": "a", "message": "x"}],
                "cursor_commits": [],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
                "ready_for_review": True,
            }
        )
        self.assertEqual(r["action"], "remind")

    def test_dependabot_coauthor_ignored(self):
        r = mod.decide(
            {
                "body": "",
                "commits": [
                    {
                        "sha": "a",
                        "message": "bump\n\nCo-Authored-By: dependabot[bot] <x@users.noreply.github.com>\n",
                    }
                ],
                "cursor_commits": [],
                "pr_user": "alice",
                "current_labels": [],
                "comments": [],
            }
        )
        self.assertEqual(r["signal"], "none")


if __name__ == "__main__":
    unittest.main()
