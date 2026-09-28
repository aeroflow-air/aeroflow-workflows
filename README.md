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

## Self-test

`.github/workflows/self-test.yml` runs on every PR and on pushes to `main`. It lints all workflows here with actionlint (`lint`) and calls `dotnet-ci.yml` locally against the tiny solution in [`tests/sample/`](tests/sample/README.md) (`dotnet-ci / build-and-test`). Both checks are required on `main`, so a change to a reusable workflow is proven here before it is tagged.
