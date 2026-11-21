# Changelog

Release notes for tags before this file lived in [GitHub Releases](https://github.com/aeroflow-air/aeroflow-workflows/releases).

## Unreleased

Nothing yet.

## v0.7.0

- `sync-agent-skills.yml` (ADR-0023): reusable workflow that keeps a repo's pinned copy of `aeroflow-air/agent-skills` in `.claude/skills/` honest. `mode: check` (pull requests, `contents: read`) fails when any `.claude/skills/aeroflow-*` folder differs from the release pinned in `.agent-skills.yaml`, minus its `exclude` list. `mode: bump` (schedule or dispatch) finds the latest release, bumps `version:`, re-syncs and opens or updates one PR from `chore/agent-skills-sync` (`contents: write`, `pull-requests: write`, or an optional GitHub App token via `app-id` + `app-private-key` so CI runs on the PR). Squad-owned skills (any other folder name) are never touched.
- `scripts/sync_agent_skills.py`: the stdlib check/sync script behind it, with unit tests in `tests/agent-skills-sync/`.
- Self-test: `sync-agent-skills-clean`, `-drift` and `-bump-dry-run` run the workflow against agent-skills v0.1.0 and two fixtures; `sync-agent-skills assert` proves clean passes, drift is caught and bump would re-sync. The unit tests run in `lint`.

## v0.6.0

- `dotnet-ci.yml`: optional `github-packages` input. When `true`, the job adds the org GitHub Packages NuGet feed (`https://nuget.pkg.github.com/aeroflow-air/index.json`) and authenticates with `GITHUB_TOKEN` via `NUGET_AUTH_TOKEN`. The default is `false`. Callers that pin `@v0.6.0` must grant `permissions.packages: read` on the job even if they leave the input off (GitHub otherwise rejects the reusable workflow at startup). Callers that stay on `@v0.5.0` or earlier are unchanged.
- Self-test: `dotnet-ci-with-feed` runs the nuget.org-only sample with the feed enabled; `dotnet-ci-github-packages` restores `AeroFlow.ServiceDefaults` 0.1.0 from the feed.

## v0.5.0 and earlier

See the [v0.5.0 release](https://github.com/aeroflow-air/aeroflow-workflows/releases/tag/v0.5.0) and earlier tags.
