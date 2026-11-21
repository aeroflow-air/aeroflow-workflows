"""Unit tests for scripts/sync_agent_skills.py (stdlib unittest, no network).

Each test builds a fake agent-skills release in a temp directory. The workflow-level
self-test (self-test.yml) runs the same checks against the real v0.1.0 release and the
fixtures in tests/agent-skills-sync/fixtures/.
"""
from __future__ import annotations

import importlib.util
import io
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_agent_skills.py"
spec = importlib.util.spec_from_file_location("sync_agent_skills", SCRIPT)
sas = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["sync_agent_skills"] = sas  # dataclasses need the module registered
spec.loader.exec_module(sas)

PIN = """source: aeroflow-air/agent-skills
version: v0.1.0   # pinned
skills: default
exclude:
  - aeroflow-c
"""


class SyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.source = self.tmp / "source"
        for name in ("aeroflow-a", "aeroflow-b", "aeroflow-c"):
            d = self.source / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
        (self.source / "skills" / "aeroflow-a" / "script.sh").write_text("echo hi\n", encoding="utf-8")
        (self.source / "default-set.txt").write_text("# default\naeroflow-a\naeroflow-b\naeroflow-c\n", encoding="utf-8")
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.config = self.repo / ".agent-skills.yaml"
        self.config.write_text(PIN, encoding="utf-8")
        self.skills = self.repo / ".claude" / "skills"
        squad = self.skills / "squad-own"
        squad.mkdir(parents=True)
        (squad / "SKILL.md").write_text("mine\n", encoding="utf-8")

    def run_cli(self, *args: str) -> int:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return sas.main([args[0], "--config", str(self.config), "--skills-dir", str(self.skills),
                             "--source-dir", str(self.source), *args[1:]])

    def pin(self):
        return sas.parse_pin(self.config)

    def test_sync_then_check_is_clean_and_leaves_squad_skills_alone(self) -> None:
        self.assertEqual(self.run_cli("sync"), 0)
        self.assertEqual(sorted(p.name for p in self.skills.iterdir()), ["aeroflow-a", "aeroflow-b", "squad-own"])
        self.assertEqual((self.skills / "squad-own" / "SKILL.md").read_text(encoding="utf-8"), "mine\n")
        self.assertEqual(self.run_cli("check"), 0)

    def test_edited_file_is_drift(self) -> None:
        self.run_cli("sync")
        (self.skills / "aeroflow-b" / "SKILL.md").write_text("edited\n", encoding="utf-8")
        self.assertEqual(self.run_cli("check"), 1)
        self.assertIn("aeroflow-b/SKILL.md: differs from v0.1.0", sas.drift(self.pin(), self.skills, self.source))

    def test_missing_skill_and_missing_file_are_drift(self) -> None:
        self.run_cli("sync")
        shutil.rmtree(self.skills / "aeroflow-b")
        (self.skills / "aeroflow-a" / "script.sh").unlink()
        problems = sas.drift(self.pin(), self.skills, self.source)
        self.assertIn("aeroflow-b: missing", problems)
        self.assertIn("aeroflow-a/script.sh: missing", problems)

    def test_extra_file_and_excluded_or_unknown_managed_folder_are_drift(self) -> None:
        self.run_cli("sync")
        (self.skills / "aeroflow-a" / "notes.md").write_text("x\n", encoding="utf-8")
        shutil.copytree(self.source / "skills" / "aeroflow-c", self.skills / "aeroflow-c")
        (self.skills / "aeroflow-zzz").mkdir()
        problems = "\n".join(sas.drift(self.pin(), self.skills, self.source))
        self.assertIn("aeroflow-a/notes.md: not in v0.1.0", problems)
        self.assertIn("aeroflow-c: unexpected managed folder (excluded", problems)
        self.assertIn("aeroflow-zzz: unexpected managed folder (not in v0.1.0", problems)

    def test_squad_skill_changes_never_count_as_drift(self) -> None:
        self.run_cli("sync")
        (self.skills / "squad-own" / "SKILL.md").write_text("changed\n", encoding="utf-8")
        self.assertEqual(self.run_cli("check"), 0)

    def test_sync_removes_stale_managed_folders(self) -> None:
        (self.skills / "aeroflow-old").mkdir()
        self.run_cli("sync")
        self.assertFalse((self.skills / "aeroflow-old").exists())

    def test_set_version_bumps_only_the_version_and_keeps_comments(self) -> None:
        self.assertEqual(self.run_cli("sync", "--set-version", "v0.2.0"), 0)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("version: v0.2.0   # pinned", text)
        self.assertIn("  - aeroflow-c", text)

    def test_explicit_list_and_inline_exclude(self) -> None:
        self.config.write_text("version: v0.1.0\nskills: [aeroflow-a, aeroflow-c]\nexclude: [aeroflow-c]\n", encoding="utf-8")
        self.run_cli("sync")
        self.assertEqual(sorted(p.name for p in self.skills.glob("aeroflow-*")), ["aeroflow-a"])
        self.assertEqual(self.pin().source, "aeroflow-air/agent-skills")

    def test_bad_configs_exit_2(self) -> None:
        for bad in ("version: main\n", "version: v1\n", "source: someone/else\nversion: v0.1.0\n",
                    "version: v0.1.0\nskills: [not-ours]\n", "version: v0.1.0\ncolour: blue\n",
                    "version: v0.1.0\nskills: [aeroflow-nope]\n"):
            with self.subTest(bad=bad):
                self.config.write_text(bad, encoding="utf-8")
                self.assertEqual(self.run_cli("check"), 2)

    def test_read_prints_source_and_version(self) -> None:
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(sas.main(["read", "--config", str(self.config)]), 0)
        self.assertEqual(out.getvalue(), "source=aeroflow-air/agent-skills\nversion=v0.1.0\n")


if __name__ == "__main__":
    unittest.main()
