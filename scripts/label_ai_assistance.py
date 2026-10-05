#!/usr/bin/env python3
"""Decide AI-assistance labels for a pull request.

Implements the detection precedence in platform-handbook ADR-0012, with
tool-telemetry preferred over trailers when a joinable signal exists:

  1. Manual lock / slash-command override
  2. PR body template markers / checkboxes
  3. Joinable tool telemetry (Cursor AI Code Tracking by commit SHA;
     Copilot cloud-agent PR authorship via GitHub actor)
  4. Commit trailers (fallback)
  5. Co-Authored-By allow-list (fallback)
  6. No signal → remind when ready_for_review

Stdlib only. Does not call vendor APIs — callers pass Cursor commit metrics
JSON when available. Never invents sources: if Cursor data is absent, that
band is skipped.

Usage:
  python3 label_ai_assistance.py --input context.json --output result.json
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

DEFAULT_COAUTHOR_ALLOWLIST = (
    "copilot",
    "copilot-swe-agent[bot]",
    "github-copilot[bot]",
    "dependabot[bot]",  # NOT used for ai-authored — filtered below
)

# Bots that author PRs and count as AI-authored when they are the PR user.
COPILOT_AGENT_LOGINS = {
    "copilot",
    "copilot-swe-agent[bot]",
    "github-copilot[bot]",
}

# Co-authored-by identities that imply AI authorship (not Dependabot).
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
    """Return the latest slash command verb, if any."""
    latest: str | None = None
    for c in comments:
        body = c.get("body") or ""
        for m in SLASH_RE.finditer(body):
            latest = m.group(1).lower()
    return latest


def body_declaration(body: str) -> set[str] | None:
    """Return content labels from body, or None if undecided."""
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


def cursor_ai_authored(
    commits: list[dict[str, Any]],
    cursor_commits: list[dict[str, Any]],
    *,
    min_ai_share: float = 0.15,
    min_composer_lines: int = 10,
) -> tuple[bool, str | None]:
    """Join PR SHAs to Cursor AI Code Tracking rows.

    Returns (matched, reason_detail). Only uses commit hashes — never user
    identity — to respect ADR-0011 teams-not-individuals for labelling.
    """
    if not cursor_commits:
        return False, None
    by_hash: dict[str, dict[str, Any]] = {}
    for row in cursor_commits:
        h = (row.get("commitHash") or row.get("commit_hash") or "").lower()
        if h:
            by_hash[h] = row
    hits: list[str] = []
    for c in commits:
        sha = (c.get("sha") or "").lower()
        if not sha:
            continue
        # full or short hash
        row = by_hash.get(sha) or next(
            (by_hash[h] for h in by_hash if h.startswith(sha[:7]) or sha.startswith(h[:7])),
            None,
        )
        if not row:
            continue
        total = int(row.get("totalLinesAdded") or row.get("total_lines_added") or 0)
        tab = int(row.get("tabLinesAdded") or row.get("tab_lines_added") or 0)
        composer = int(
            row.get("composerLinesAdded") or row.get("composer_lines_added") or 0
        )
        ai = tab + composer
        share = (ai / total) if total > 0 else (1.0 if ai > 0 else 0.0)
        if composer >= min_composer_lines or (total > 0 and share >= min_ai_share) or (
            total == 0 and ai >= min_composer_lines
        ):
            hits.append(sha[:7])
    if hits:
        return True, f"cursor-ai-code-tracking commits={','.join(hits)}"
    return False, None


def labels_from_set(content: set[str], *, auto: bool) -> tuple[list[str], list[str]]:
    """Return (add, remove) label lists."""
    add = sorted(content)
    remove = [l for l in CONTENT_LABELS if l not in content]
    if auto and ("ai-authored" in content or "ai-reviewed" in content):
        add.append(AUTO_LABEL)
    else:
        remove.append(AUTO_LABEL)
    if MANUAL_LABEL not in add:
        # leave manual label management to caller overrides
        pass
    return add, remove


def decide(ctx: dict[str, Any]) -> dict[str, Any]:
    body = ctx.get("body") or ""
    commits = ctx.get("commits") or []
    comments = ctx.get("comments") or []
    current = set(ctx.get("current_labels") or [])
    pr_user = ctx.get("pr_user")
    cursor_commits = ctx.get("cursor_commits") or []
    ready = bool(ctx.get("ready_for_review"))
    min_share = float(ctx.get("cursor_min_ai_share") or 0.15)
    min_composer = int(ctx.get("cursor_min_composer_lines") or 10)

    slash = parse_slash_commands(comments)
    manual_locked = MANUAL_LABEL in current or bool(ctx.get("manual_lock"))

    # --- Band 1: slash / manual ---
    if slash == "unlock":
        return {
            "action": "unlock",
            "labels_add": [],
            "labels_remove": [MANUAL_LABEL],
            "manual_lock": False,
            "signal": "slash-unlock",
            "reason": "Manual lock cleared via /ai-label unlock; re-evaluate on next event.",
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
        else:  # clear
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

    # --- Band 2: body markers ---
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

    # --- Band 3: joinable tool telemetry ---
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
                f"`{pr_user}` matches Copilot cloud agent. "
                "Disagree? Comment `/ai-label none` or `/ai-label clear`."
            ),
        }

    hit, detail = cursor_ai_authored(
        commits,
        cursor_commits,
        min_ai_share=min_share,
        min_composer_lines=min_composer,
    )
    if hit:
        content = {"ai-authored"}
        add, remove = labels_from_set(content, auto=True)
        return {
            "action": "apply",
            "labels_add": add,
            "labels_remove": remove,
            "manual_lock": False,
            "signal": "cursor-ai-code-tracking",
            "reason": detail,
            "comment": (
                f"Auto-applied `ai-authored` (`{AUTO_LABEL}`) from Cursor AI Code "
                f"Tracking ({detail}). "
                "Disagree? Comment `/ai-label none` or `/ai-label clear`.\n\n"
                "Docs: https://cursor.com/docs/account/teams/ai-code-tracking-api"
            ),
        }

    # --- Band 4: trailers (fallback) ---
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
                f"(`{AUTO_LABEL}`) from `Ai-Assisted` commit trailer(s) — fallback "
                "when no joinable tool telemetry matched. "
                "Disagree? `/ai-label clear` or fix the trailer."
            ),
        }

    # --- Band 5: co-authored-by allow-list (fallback) ---
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
                "trailer matching the AI agent allow-list (fallback). "
                "Disagree? `/ai-label none`."
            ),
        }

    # --- Band 6: none ---
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
    p.add_argument("--input", required=True, help="Path to context JSON")
    p.add_argument("--output", required=True, help="Path to write result JSON")
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
