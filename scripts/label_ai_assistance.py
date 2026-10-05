#!/usr/bin/env python3
"""Decide AI-assistance labels for a pull request (ADR-0012, zero-cost).

Precedence:
  1. Manual lock / slash-command override
  2. PR body template markers / checkboxes
  3. Copilot cloud-agent PR author (GitHub-native, free)
  4. Commit trailers (fallback)
  5. Co-Authored-By allow-list (fallback)
  6. No signal → remind when ready_for_review

No paid/Enterprise vendor APIs. No nightly collector.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

CONTENT_LABELS = ("ai-authored", "ai-reviewed", "ai-declaration:none")
AUTO_LABEL = "ai-label:auto"
MANUAL_LABEL = "ai-label:manual"

COPILOT_AGENT_LOGINS = {
    "copilot",
    "copilot-swe-agent[bot]",
    "github-copilot[bot]",
}

AI_COAUTHOR_PATTERNS = (
    re.compile(r"copilot", re.I),
    re.compile(r"github-copilot", re.I),
    re.compile(r"cursoragent", re.I),
    re.compile(r"claude\s*<", re.I),
)

TRAILER_RE = re.compile(
    r"^Ai-Assisted:\s*(authored|reviewed|none)\s*$",
    re.I | re.M,
)
COAUTHOR_RE = re.compile(
    r"^Co-Authored-By:\s*(.+?)(?:\s*<([^>]+)>)?\s*$",
    re.I | re.M,
)
SLASH_RE = re.compile(
    r"(?m)^/ai-label\s+(authored|reviewed|both|none|clear|unlock)\b",
    re.I,
)
BODY_MARKER_RE = re.compile(
    r"<!--\s*ai-label:\s*(authored|reviewed|none)\s*-->",
    re.I,
)
CHECKBOX_AUTHORED = re.compile(
    r"^\s*[-*]\s*\[x\]\s*`?ai-authored`?",
    re.I | re.M,
)
CHECKBOX_REVIEWED = re.compile(
    r"^\s*[-*]\s*\[x\]\s*`?ai-reviewed`?",
    re.I | re.M,
)
CHECKBOX_NEITHER = re.compile(
    r"^\s*[-*]\s*\[x\]\s*`?neither`?",
    re.I | re.M,
)


def _norm_login(login: str | None) -> str:
    return (login or "").strip().lower()


def parse_slash_commands(comments: list[dict[str, Any]]) -> str | None:
    latest: str | None = None
    for c in comments:
        body = c.get("body") or ""
        for m in SLASH_RE.finditer(body):
            latest = m.group(1).lower()
    return latest


def body_declaration(body: str) -> set[str] | None:
    found: set[str] = set()
    for m in BODY_MARKER_RE.finditer(body or ""):
        kind = m.group(1).lower()
        if kind == "authored":
            found.add("ai-authored")
        elif kind == "reviewed":
            found.add("ai-reviewed")
        elif kind == "none":
            found.add("ai-declaration:none")
    if CHECKBOX_AUTHORED.search(body or ""):
        found.add("ai-authored")
    if CHECKBOX_REVIEWED.search(body or ""):
        found.add("ai-reviewed")
    if CHECKBOX_NEITHER.search(body or ""):
        found.add("ai-declaration:none")
    if not found:
        return None
    if "ai-declaration:none" in found and (
        "ai-authored" in found or "ai-reviewed" in found
    ):
        found.discard("ai-declaration:none")
    return found


def trailer_declaration(commits: list[dict[str, Any]]) -> set[str] | None:
    found: set[str] = set()
    for c in commits:
        msg = c.get("message") or ""
        for m in TRAILER_RE.finditer(msg):
            kind = m.group(1).lower()
            if kind == "authored":
                found.add("ai-authored")
            elif kind == "reviewed":
                found.add("ai-reviewed")
            elif kind == "none":
                found.add("ai-declaration:none")
    if not found:
        return None
    if "ai-declaration:none" in found and (
        "ai-authored" in found or "ai-reviewed" in found
    ):
        found.discard("ai-declaration:none")
    return found


def coauthor_ai(commits: list[dict[str, Any]]) -> bool:
    for c in commits:
        msg = c.get("message") or ""
        for m in COAUTHOR_RE.finditer(msg):
            identity = f"{m.group(1)} <{m.group(2) or ''}>"
            if re.search(r"dependabot", identity, re.I):
                continue
            for pat in AI_COAUTHOR_PATTERNS:
                if pat.search(identity):
                    return True
    return False


def copilot_cloud_agent(pr_user: str | None) -> bool:
    return _norm_login(pr_user) in {_norm_login(x) for x in COPILOT_AGENT_LOGINS}


def labels_from_set(content: set[str], *, auto: bool) -> tuple[list[str], list[str]]:
    add = sorted(content)
    remove = [l for l in CONTENT_LABELS if l not in content]
    if auto and ("ai-authored" in content or "ai-reviewed" in content):
        add.append(AUTO_LABEL)
    else:
        remove.append(AUTO_LABEL)
    return add, remove


def decide(ctx: dict[str, Any]) -> dict[str, Any]:
    body = ctx.get("body") or ""
    commits = ctx.get("commits") or []
    comments = ctx.get("comments") or []
    current = set(ctx.get("current_labels") or [])
    pr_user = ctx.get("pr_user")
    ready = bool(ctx.get("ready_for_review"))

    slash = parse_slash_commands(comments)
    manual_locked = MANUAL_LABEL in current or bool(ctx.get("manual_lock"))

    if slash == "unlock":
        return {
            "action": "unlock",
            "labels_add": [],
            "labels_remove": [MANUAL_LABEL],
            "manual_lock": False,
            "signal": "slash-unlock",
            "reason": "Manual lock cleared via /ai-label unlock",
            "comment": (
                "Cleared `ai-label:manual`. Automation may re-evaluate on the next "
                "pull_request event."
            ),
        }

    if slash in {"authored", "reviewed", "both", "none", "clear"}:
        if slash == "authored":
            content = {"ai-authored"}
        elif slash == "reviewed":
            content = {"ai-reviewed"}
        elif slash == "both":
            content = {"ai-authored", "ai-reviewed"}
        elif slash == "none":
            content = {"ai-declaration:none"}
        else:
            content = set()
        add, remove = labels_from_set(content, auto=False)
        add.append(MANUAL_LABEL)
        remove = [l for l in remove if l != MANUAL_LABEL]
        if AUTO_LABEL not in remove:
            remove.append(AUTO_LABEL)
        return {
            "action": "apply",
            "labels_add": sorted(set(add)),
            "labels_remove": sorted(set(remove) | (set(CONTENT_LABELS) - content)),
            "manual_lock": True,
            "signal": f"slash-{slash}",
            "reason": f"Auditable override via /ai-label {slash}",
            "comment": (
                f"Applied labels from `/ai-label {slash}` (manual lock set; "
                f"`{AUTO_LABEL}` cleared)."
            ),
        }

    if manual_locked:
        return {
            "action": "noop",
            "labels_add": [],
            "labels_remove": [],
            "manual_lock": True,
            "signal": "manual-lock",
            "reason": "Manual lock present; automation will not change content labels.",
            "comment": None,
        }

    body_labels = body_declaration(body)
    if body_labels is not None:
        add, remove = labels_from_set(body_labels, auto=False)
        return {
            "action": "apply",
            "labels_add": add,
            "labels_remove": remove,
            "manual_lock": False,
            "signal": "body-marker",
            "reason": f"PR body declared {sorted(body_labels)}",
            "comment": (
                f"Applied {', '.join(f'`{l}`' for l in sorted(body_labels))} from "
                "PR description / template checkboxes."
            ),
        }

    if copilot_cloud_agent(pr_user):
        content = {"ai-authored"}
        add, remove = labels_from_set(content, auto=True)
        return {
            "action": "apply",
            "labels_add": add,
            "labels_remove": remove,
            "manual_lock": False,
            "signal": "copilot-cloud-agent",
            "reason": f"PR user `{pr_user}` is a Copilot cloud-agent identity",
            "comment": (
                f"Auto-applied `ai-authored` (`{AUTO_LABEL}`) because the PR author "
                f"`{pr_user}` matches Copilot cloud agent (zero-cost GitHub signal). "
                "Disagree? Comment `/ai-label none` or `/ai-label clear`."
            ),
        }

    trailers = trailer_declaration(commits)
    if trailers is not None:
        add, remove = labels_from_set(trailers, auto=True)
        return {
            "action": "apply",
            "labels_add": add,
            "labels_remove": remove,
            "manual_lock": False,
            "signal": "commit-trailer",
            "reason": f"Commit trailer(s) declared {sorted(trailers)}",
            "comment": (
                f"Auto-applied {', '.join(f'`{l}`' for l in sorted(trailers))} "
                f"(`{AUTO_LABEL}`) from `Ai-Assisted` commit trailer(s). "
                "Disagree? `/ai-label clear`."
            ),
        }

    if coauthor_ai(commits):
        content = {"ai-authored"}
        add, remove = labels_from_set(content, auto=True)
        return {
            "action": "apply",
            "labels_add": add,
            "labels_remove": remove,
            "manual_lock": False,
            "signal": "co-authored-by",
            "reason": "Co-Authored-By matches AI agent allow-list",
            "comment": (
                f"Auto-applied `ai-authored` (`{AUTO_LABEL}`) from `Co-Authored-By` "
                "trailer matching the AI agent allow-list. "
                "Disagree? `/ai-label none`."
            ),
        }

    undeclared = not any(l in current for l in CONTENT_LABELS)
    if ready and undeclared:
        return {
            "action": "remind",
            "labels_add": [],
            "labels_remove": [],
            "manual_lock": False,
            "signal": "none",
            "reason": "No AI-assistance declaration; ready for review",
            "comment": (
                "Reminder: please declare AI assistance before merge — tick the PR "
                "template (`ai-authored` / `ai-reviewed` / Neither) or comment "
                "`/ai-label authored|reviewed|none`. "
                "This check is non-blocking (ADR-0012 Phase B)."
            ),
        }

    return {
        "action": "noop",
        "labels_add": [],
        "labels_remove": [],
        "manual_lock": False,
        "signal": "none",
        "reason": "No decisive signal",
        "comment": None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    with open(args.input, encoding="utf-8") as f:
        ctx = json.load(f)
    result = decide(ctx)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"action": result["action"], "signal": result["signal"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
