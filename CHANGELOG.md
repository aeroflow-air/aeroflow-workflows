# Changelog

Release notes for tags before this file lived in [GitHub Releases](https://github.com/aeroflow-air/aeroflow-workflows/releases).

## Unreleased (proposed v0.6.0)

- `dotnet-ci.yml`: optional `github-packages` input. When `true`, the job adds the org GitHub Packages NuGet feed (`https://nuget.pkg.github.com/aeroflow-air/index.json`) and authenticates with `GITHUB_TOKEN` via `NUGET_AUTH_TOKEN`. Callers must set `permissions.packages: read` on the job. The default is `false`. The reusable workflow *allows* `packages: read` but does not require it, so a caller that only grants `contents: read` still starts and behaves as before.
- Self-test: `dotnet-ci-with-feed` runs the nuget.org-only sample with the feed enabled; `dotnet-ci-github-packages` restores `AeroFlow.ServiceDefaults` 0.1.0 from the feed.

## v0.5.0 and earlier

See the [v0.5.0 release](https://github.com/aeroflow-air/aeroflow-workflows/releases/tag/v0.5.0) and earlier tags.
