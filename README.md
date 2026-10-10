# aeroflow-workflows

Reusable GitHub Actions workflows for the aeroflow-air org. Callers pin by **tag** (not `main`).

## Workflows

| Workflow | Purpose | Tag example |
|----------|---------|-------------|
| `validate-decisions.yml` | ADR shape, lifecycle, immutability | `@v1` (tag pending) |
| `dotnet-ci.yml` | .NET restore → build → test | `@v0.1.0` |
| `workload-deploy.yml` | ADR-0009 shared deploy: validate `workload.yaml`, generate Bicep, `bicep build` + `lint` (no Azure yet) | pin a tag after merge |
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

## Workload generator and shared deploy workflow (ADR-0009)

- [`generator/generate.py`](generator/README.md) validates a `workload.yaml` against the schema and writes a Bicep composition that references `br/platform:*` modules. `http` and `identity` map to `container-app-service`; `store` and `queue` fail as not yet supported.
- [`modules/`](modules/README.md) holds a local stand-in for `container-app-service` (copied from `infra-platform`), because no module is published yet. `--local-modules` compiles against it.
- `.github/workflows/workload-deploy.yml` (`workflow_call`) checks out the caller, generates, runs `bicep build` and `bicep lint`, and uploads the Bicep as the `workload-bicep` artifact. What-if and deploy are a gated TODO: zero cost, no Azure login.

```yaml
jobs:
  workload:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/workload-deploy.yml@<tag>
    with:
      workflows_ref: <tag>   # keep in sync with the uses: pin above
    permissions:
      contents: read
```

## Self-test

`.github/workflows/self-test.yml` runs on every PR and on pushes to `main`. The `lint` job lints all workflows here with actionlint and validates the workload schema. The `dotnet-ci` job calls `dotnet-ci.yml` locally against the tiny solution in [`tests/sample/`](tests/sample/README.md) (`dotnet-ci / build-and-test`). Both checks are required on `main`, so a change to a reusable workflow is proven here before it is tagged.

## AI assistance labels (ADR-0012)

Phase B automation: applies `ai-authored` / `ai-reviewed` / `ai-declaration:none` on pull requests.

**Zero-cost signals only** (no paid/Enterprise vendor APIs):

1. Manual `/ai-label` slash commands (locks with `ai-label:manual`)
2. PR body template markers / checkboxes
3. Copilot cloud-agent PR author login (GitHub-native)
4. `Ai-Assisted:` commit trailers (fallback)
5. AI `Co-Authored-By` allow-list (fallback)
6. Reminder when ready for review and undeclared (non-blocking)

Aggregate vendor metrics (Copilot Usage Metrics, Claude Code Analytics, Windsurf, Cursor AI Code Tracking) are **out of scope** for labelling — team dashboards only if already licensed (ADR-0011).

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
    permissions:
      contents: read
      pull-requests: write
```

No secrets required. Permissions on the job: `contents: read`, `pull-requests: write` only.

