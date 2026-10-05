# aeroflow-workflows

Reusable GitHub Actions workflows for the aeroflow-air org. Callers pin by **tag** (not `main`).

## Workflows

| Workflow | Purpose | Tag example |
|----------|---------|-------------|
| `validate-decisions.yml` | ADR shape, lifecycle, immutability | `@v1` (tag pending) |
| `dotnet-ci.yml` | .NET restore → build → test | `@v0.1.0` |
| `label-ai-assistance.yml` | ADR-0012 AI PR labels (Cursor commit join + Copilot agent + fallbacks) | pin same ref as `workflows_ref` |

## .NET CI

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  build-and-test:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/dotnet-ci.yml@v0.1.0
    with:
      solution: Your.Service.sln   # optional; defaults to repo root
      # dotnet-version: "8.0.x"   # optional
    permissions:
      contents: read
```

Green means: restore, Release build, and tests all succeed. No format/coverage/CodeQL gates here — keep those opt-in and justified.

## Decision validation

See `platform-handbook/docs/decisions/README.md`. Service repos with `docs/decisions/` call:

```yaml
jobs:
  decisions:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/validate-decisions.yml@v1
```

## Workload manifest schema

[`schemas/workload.schema.json`](schemas/README.md) is the JSON Schema for `workload.yaml` (ADR-0009). It is versioned with this repo's tags. `v0.1.0` does not include it. Detail, including what the schema refuses, is in [`schemas/README.md`](schemas/README.md).

## Self-test

`.github/workflows/self-test.yml` runs on every PR and on pushes to `main`. The `lint` job lints all workflows here with actionlint and validates the workload schema. The `dotnet-ci` job calls `dotnet-ci.yml` locally against the tiny solution in [`tests/sample/`](tests/sample/README.md) (`dotnet-ci / build-and-test`). Both checks are required on `main`, so a change to a reusable workflow is proven here before it is tagged.

## AI assistance labels (ADR-0012)

Phase B automation: applies `ai-authored` / `ai-reviewed` / `ai-declaration:none` on pull requests.

**Joinable tool signals (preferred over trailers):**

- [Cursor AI Code Tracking](https://cursor.com/docs/account/teams/ai-code-tracking-api) — per-commit SHA metrics (Enterprise, alpha). Optional secret `CURSOR_API_KEY`.
- Copilot cloud agent — detected via PR author login on GitHub (no metrics API).

**Not used for labelling** (no PR/commit attribution): Copilot Usage Metrics API, Claude Code Analytics API, Windsurf Analytics. Keep them for org dashboards only (ADR-0011).

**Fallbacks:** `Ai-Assisted:` commit trailers, AI `Co-Authored-By` allow-list, PR template checkboxes (highest after manual lock).

```yaml
name: AI assistance labels

on:
  pull_request:
    types: [opened, edited, synchronize, ready_for_review, reopened]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write

jobs:
  label:
    if: github.event_name == 'pull_request' || github.event.issue.pull_request
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/label-ai-assistance.yml@main
    with:
      workflows_ref: main   # keep in sync with the uses: pin above
    secrets:
      CURSOR_API_KEY: ${{ secrets.CURSOR_API_KEY }}  # optional; placeholder skips Cursor band
    permissions:
      contents: read
      pull-requests: write
```

Org/repo secrets (placeholders — do not commit real values):

| Secret | Required | Purpose |
|--------|----------|---------|
| `CURSOR_API_KEY` | No | Cursor Enterprise API key (`admin:*`) for AI Code Tracking. Use `REPLACE_WITH_CURSOR_ENTERPRISE_API_KEY` until issued. |

Permissions on the job: `contents: read`, `pull-requests: write` only.

