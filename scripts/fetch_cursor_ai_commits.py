#!/usr/bin/env python3
"""Fetch Cursor AI Code Tracking commit metrics; emit hash-only JSON.

Requires CURSOR_API_KEY in the environment (Basic auth, key as username).
Enterprise + AI Code Tracking access only — see:
https://cursor.com/docs/account/teams/ai-code-tracking-api

Privacy: drops userId / userEmail so Actions logs and artefacts never carry
per-person usage (ADR-0011 teams-not-individuals).

If the key is missing or the API errors, writes an empty list and exits 0 so
the label workflow can fall back to trailers / co-authors.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def fetch(api_key: str, start: str, end: str, page_size: int = 1000) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        q = urllib.parse.urlencode(
            {
                "startDate": start,
                "endDate": end,
                "page": page,
                "pageSize": page_size,
            }
        )
        url = f"https://api.cursor.com/analytics/ai-code/commits?{q}"
        req = urllib.request.Request(url, method="GET")
        # Basic auth: key as username, empty password
        import base64

        token = base64.b64encode(f"{api_key}:".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.load(resp)
        batch = payload.get("items") or []
        for row in batch:
            items.append(
                {
                    "commitHash": row.get("commitHash"),
                    "repoName": row.get("repoName"),
                    "branchName": row.get("branchName"),
                    "totalLinesAdded": row.get("totalLinesAdded"),
                    "totalLinesDeleted": row.get("totalLinesDeleted"),
                    "tabLinesAdded": row.get("tabLinesAdded"),
                    "tabLinesDeleted": row.get("tabLinesDeleted"),
                    "composerLinesAdded": row.get("composerLinesAdded"),
                    "composerLinesDeleted": row.get("composerLinesDeleted"),
                    "commitSource": row.get("commitSource"),
                    # intentionally omit userId / userEmail
                }
            )
        total = int(payload.get("totalCount") or 0)
        if page * page_size >= total or not batch:
            break
        page += 1
    return items


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--start", default="14d")
    p.add_argument("--end", default="now")
    p.add_argument(
        "--repo-filter",
        default="",
        help="Optional substring match on repoName (e.g. aeroflow-air/svc-x)",
    )
    args = p.parse_args(argv)
    key = os.environ.get("CURSOR_API_KEY", "").strip()
    if not key or key.startswith("REPLACE_") or key == "placeholder":
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump([], f)
        print("cursor_fetch: skipped (CURSOR_API_KEY unset or placeholder)")
        return 0
    try:
        items = fetch(key, args.start, args.end)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
        print(f"cursor_fetch: API error ({e.__class__.__name__}); writing empty list", file=sys.stderr)
        items = []
    if args.repo_filter:
        needle = args.repo_filter.lower()
        items = [i for i in items if needle in (i.get("repoName") or "").lower()]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(items, f)
        f.write("\n")
    print(f"cursor_fetch: wrote {len(items)} commit rows (user fields redacted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
