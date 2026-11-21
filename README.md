# aeroflow-workflows

Reusable GitHub Actions workflows for the aeroflow-air org. Callers pin by **tag** (not `main`).

## Workflows

| Workflow | Purpose | Tag example |
|----------|---------|-------------|
| `validate-decisions.yml` | ADR shape, lifecycle, immutability | `@v1` (tag pending) |
| `dotnet-ci.yml` | .NET restore → build → test (optional org GitHub Packages feed) | `@v0.6.0` (needs `packages: read`) |
| `workload-deploy.yml` | ADR-0009 shared deploy: validate `workload.yaml`, generate Bicep, `bicep build` + `lint` (no Azure yet) | pin a tag after merge |
| `label-ai-assistance.yml` | ADR-0012 AI PR labels (Cursor commit join + Copilot agent + fallbacks) | pin same ref as `workflows_ref` |
| `ai-code-review.yml` | Advisory Claude PR review tuned to AeroFlow standards | `@v0.3.1` |
| `sync-agent-skills.yml` | ADR-0023: check `.claude/skills/aeroflow-*` against the pinned agent-skills release; bump PRs | proposed `@v0.7.0` |

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

### GitHub Packages (optional, v0.6.0)

To restore packages from the org feed (`https://nuget.pkg.github.com/aeroflow-air/index.json`), such as `AeroFlow.ServiceDefaults`, set `github-packages: true` and grant `packages: read` on the calling job. Authentication uses `GITHUB_TOKEN` (`NUGET_AUTH_TOKEN`). Do not put a PAT in the workflow.

Leave the input unset or `false` if the repo only uses nuget.org. **When bumping the pin to `@v0.6.0`, add `packages: read` on the calling job even if you do not enable the feed.** GitHub rejects the reusable workflow at startup if the caller only grants `contents: read`. Callers that stay on `@v0.5.0` need no change.

```yaml
jobs:
  build-and-test:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/dotnet-ci.yml@v0.6.0
    with:
      solution: Your.Service.sln
      github-packages: true
    permissions:
      contents: read
      packages: read
```

Upgrade without using the feed (one-line permissions change only):

```yaml
jobs:
  build-and-test:
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/dotnet-ci.yml@v0.6.0
    with:
      solution: Your.Service.sln
    permissions:
      contents: read
      packages: read
```

`v0.6.0` is the proposed next tag for this change; do not pin it until the tag exists. Local `dotnet restore` still needs a user-level PAT with `read:packages` — see [lib-service-defaults](https://github.com/aeroflow-air/lib-service-defaults#consume). This workflow does not create that token.

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

## Agent skills sync (ADR-0023)

A repo pins a release of [agent-skills](https://github.com/aeroflow-air/agent-skills) in `.agent-skills.yaml` and keeps a copy in `.claude/skills/`, where Claude Code, Copilot and any agent reading the repo find it:

```yaml
# .agent-skills.yaml
source: aeroflow-air/agent-skills   # optional, the default
version: v0.1.0                     # release tag
skills: default                     # default-set.txt of that release, or a list
exclude: []                         # platform skills this repo replaces with its own
```

`sync-agent-skills.yml` manages only `.claude/skills/aeroflow-*`. A squad's own skill uses any other folder name and is never touched. To replace a platform skill, list it under `exclude` and add one with a different name.

| Mode | When | Caller permissions | What it does |
|------|------|--------------------|--------------|
| `check` | `pull_request` | `contents: read` | Fails if a managed folder is missing, extra, excluded-but-present, or differs byte for byte from the pinned tag |
| `bump` | `schedule`, `workflow_dispatch` | `contents: write`, `pull-requests: write` (or `contents: read` with an app token) | Finds the latest release, bumps `version:`, re-syncs, opens or updates one PR from `chore/agent-skills-sync`. Run it from the default branch |

```yaml
name: Agent skills

on:
  pull_request:
  schedule: [{ cron: "23 6 * * 1" }]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  check:
    if: github.event_name == 'pull_request'
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/sync-agent-skills.yml@v0.7.0
    with:
      mode: check
      workflows_ref: v0.7.0
    permissions:
      contents: read

  bump:
    if: github.event_name != 'pull_request'
    uses: aeroflow-air/aeroflow-workflows/.github/workflows/sync-agent-skills.yml@v0.7.0
    with:
      mode: bump
      workflows_ref: v0.7.0
      # app-id: ${{ vars.AGENT_SKILLS_APP_ID }}        # optional, see below
    # secrets:
    #   app-private-key: ${{ secrets.AGENT_SKILLS_APP_KEY }}
    permissions:
      contents: write
      pull-requests: write
```

**CI on the bump PR.** A PR opened with `GITHUB_TOKEN` does not trigger other workflows, so its required checks never run. Either close and reopen the PR (the PR body says so), or pass `app-id` and the `app-private-key` secret of a GitHub App installed on the repo with Contents and Pull requests read & write. The PR is then opened with a short-lived app token and CI runs normally. No org app exists for this yet.

Locally: `python3 scripts/sync_agent_skills.py sync --source-dir <agent-skills checkout at the pinned tag>` from the repo root, then `check` to confirm.

Inputs: `mode` and `workflows_ref` (required), `path` (default `.`), `fail-on-drift` (check, default `true`), `dry-run` (bump, default `false`), `app-id`. Outputs: `drift`, `changed`, `version`.

## Self-test

`.github/workflows/self-test.yml` runs on every PR and on pushes to `main`. The `lint` job lints all workflows here with actionlint and validates the workload schema. The `dotnet-ci` job calls `dotnet-ci.yml` locally against the tiny solution in [`tests/sample/`](tests/sample/README.md) (`dotnet-ci / build-and-test`). Two further jobs prove the optional GitHub Packages feed: `dotnet-ci-with-feed` runs the same sample with `github-packages: true`, and `dotnet-ci-github-packages` restores `AeroFlow.ServiceDefaults` 0.1.0 from the org feed ([`tests/sample-github-packages/`](tests/sample-github-packages/README.md)). The `sync-agent-skills-*` jobs run `sync-agent-skills.yml` against agent-skills v0.1.0 and the fixtures in `tests/agent-skills-sync/fixtures/`. `sync-agent-skills assert` proves the clean fixture passes, the drift fixture is caught, and a bump dry run would re-sync it. `lint` and `dotnet-ci / build-and-test` are required on `main`.

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
