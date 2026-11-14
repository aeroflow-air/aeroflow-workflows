# aeroflow-workflows

Reusable GitHub Actions workflows for the aeroflow-air org. Callers pin by **tag** (not `main`).

## Workflows

| Workflow | Purpose | Tag example |
|----------|---------|-------------|
| `validate-decisions.yml` | ADR shape, lifecycle, immutability | `@v1` (tag pending) |
| `dotnet-ci.yml` | .NET restore → build → test | `@v0.1.0` |
| `workload-deploy.yml` | ADR-0009 shared deploy: validate `workload.yaml`, generate Bicep, `bicep build` + `lint` (no Azure yet) | pin a tag after merge |
| `label-ai-assistance.yml` | ADR-0012 AI PR labels (Cursor commit join + Copilot agent + fallbacks) | pin same ref as `workflows_ref` |
| `ai-code-review.yml` | Advisory Claude PR review tuned to AeroFlow standards | `@v0.3.1` |

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
- `.github/workflows/workload-deploy.yml` (`workflow_call`) checks out the caller, generates with Python by default (`generator: csharp` opts in to `generate.cs`), runs `bicep build` and `bicep lint`, analyses the generated Bicep with PSRule for Azure, and uploads the Bicep plus the SARIF report as the `workload-bicep` artifact. What-if and deploy are a gated TODO: zero cost, no Azure login.

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
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/label-ai-assistance.yml@v0.5.0
    with:
      workflows_ref: v0.5.0   # keep in sync with the uses: pin above
    permissions:
      contents: read
      pull-requests: write
```

No secrets required. Permissions on the job: `contents: read`, `pull-requests: write` only.


## AI code review

`ai-code-review.yml` runs an advisory PR review with the official
[`anthropics/claude-code-action@v1`](https://github.com/anthropics/claude-code-action),
using a prompt tuned to AeroFlow standards (event contracts, `docs/service.md`,
tests, security, .NET 8, and ADR-0004 domain conventions from the
[coding standards](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/standards/coding-standards.md)
and the repo's `CLAUDE.md`, which the action loads automatically). It posts inline comments and one sticky summary
comment; it never approves, blocks or pushes.

```yaml
on:
  pull_request:
    types: [opened, synchronize, ready_for_review, reopened]

jobs:
  ai-review:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/ai-code-review.yml@v0.3.1
    secrets:
      anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
    permissions:
      contents: read
      pull-requests: write
      id-token: write   # OIDC exchange for the Claude GitHub app token
```

Cost guards and skips: drafts, PRs labelled `skip-ai-review`, PRs over
`max-changed-lines` (default 1500) and `max-turns` (default 25). Hitting the turn cap, or any other failure of the
review step, shows as a warning rather than failing the job, since the review is advisory. Fork PRs are
skipped because GitHub does not pass secrets to them. Needs the Claude GitHub
app installed on the org and the `ANTHROPIC_API_KEY` org secret visible to the
calling repo. Inputs: `max-turns`, `max-changed-lines`, `skip-label`, `model`,
`extra-instructions`. Not a required check. Put repo conventions in a
`CLAUDE.md` at the repo root rather than in `extra-instructions`.

## PSRule for Azure (workload-deploy.yml)

After `bicep build` and `bicep lint`, `workload-deploy.yml` runs [PSRule for Azure](https://azure.github.io/PSRule.Rules.Azure/) (`microsoft/ps-rule@v2.9.0`, `PSRule.Rules.Azure`, baseline `Azure.GA_2025_12`) on the generated `main.bicep`, whichever generator produced it (Python by default, or `generator: csharp`), with Bicep expansion so the module stand-ins are checked too. It runs offline with no Azure login. The job fails on any rule failure or error. A summary goes to the job page, and a SARIF report is uploaded with the `workload-bicep` artifact.

- Config: [`ps-rule.yaml`](ps-rule.yaml). It holds placeholder values for parameters without defaults (expansion only), uses a `uksouth` placeholder resource group, and allows UK regions.
- Suppressions: [`.ps-rule/suppressions.Rule.yaml`](.ps-rule/suppressions.Rule.yaml). They are scoped to resources tagged `aeroflow-module: container-app-service:*`.

| Rule | Why it's suppressed |
| --- | --- |
| `Azure.ContainerApp.AvailabilityZone` | Zero-cost Consumption environment (ADR-0007); zones need a dedicated environment and subnet. |
| `Azure.ContainerApp.MinReplicas` | Scale to zero on purpose; 2+ replicas is standing cost. |
| `Azure.Log.Replication` | One log workspace for a learning platform; replication adds cost. |
| `Azure.ContainerApp.PublicAccess` | No platform VNet yet; ingress is `internal` by default. Remove the suppression when the module gets VNet integration. |
| `Azure.ContainerApp.RestrictIngress` | No IP restrictions until there is a platform network or Front Door. Same follow-up. |

Run it locally (PowerShell 7, `Install-Module PSRule.Rules.Azure`, bicep on PATH):

```powershell
Assert-PSRule -InputPath out/main.bicep -Module PSRule.Rules.Azure -Baseline Azure.GA_2025_12 -Option ps-rule.yaml -Path .ps-rule/ -Outcome Fail,Error
```
