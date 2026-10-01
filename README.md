# aeroflow-workflows

Reusable GitHub Actions workflows for the aeroflow-air org. Callers pin by **tag** (not `main`).

## Workflows

| Workflow | Purpose | Tag example |
|----------|---------|-------------|
| `validate-decisions.yml` | ADR shape, lifecycle, immutability | `@v1` (tag pending) |
| `dotnet-ci.yml` | .NET restore → build → test | `@v0.1.0` |

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
