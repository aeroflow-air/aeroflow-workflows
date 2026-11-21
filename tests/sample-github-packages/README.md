# GitHub Packages self-test sample

This solution exists only to exercise `.github/workflows/dotnet-ci.yml` with
`github-packages: true`. It references `AeroFlow.ServiceDefaults` 0.1.0 from
the org GitHub Packages feed and has one xUnit test that the package restored.

It is not a template. Keep it as small as possible. Local restore needs a
user-level PAT with `read:packages`; CI uses `GITHUB_TOKEN`.
