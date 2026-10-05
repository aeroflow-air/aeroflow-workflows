# Workload manifest schema

`workload.schema.json` is the JSON Schema (draft 2020-12) for a service repo's `workload.yaml`.

There was no schema directory in this repo. The schema sits here, next to the workflows, because ADR-0009 says it lives in `aeroflow-workflows` and is versioned with this repo's tags.

It validates a request, not a deployment. ADR-0009 says the shared deploy workflow generates the composition from the manifest and that the output is not committed. This schema does not deploy anything and does not describe Azure resources.

## What it allows

The root object has `additionalProperties: false`. The properties are:

- `workload` (string, required)
- `repo` (string, required)
- `dataClass` (string, required), enum `public`, `internal`, `confidential`
- `capabilities` (array, required). Each item is one of `http`, `identity`, `store`, `queue`. Items must be unique.
- `modules` (object, optional). When present it requires `hosting`, a string matching either `br/platform:<module>:<major>.<minor>.<patch>` or `br:ghcr.io/aeroflow-air/<module>:<major>.<minor>.<patch>`. The module name is a single segment (`[a-z][a-z0-9-]*`) and is not fixed to `container-app-service`. No other key is allowed.

ADR-0009's example is:

```yaml
workload: flight-status
repo: svc-flight-status
dataClass: internal
capabilities: [http, identity]
modules:
  hosting: br/platform:container-app-service:x.y.z
```

`x.y.z` in that example is a placeholder. The schema requires a numeric `major.minor.patch` with no leading `v` and no pre-release. It does not fix the module name to `container-app-service`. The same version rule applies to a GitHub Container Registry pin, for example `br:ghcr.io/aeroflow-air/container-app-service:0.1.0`. Only the `ghcr.io/aeroflow-air/` registry path is accepted alongside the existing `br/platform` alias.

## What it refuses

An unknown root key fails. That is how a raw resource block, an arbitrary Bicep or ARM resource, or any other free-form infrastructure key is refused: those keys are not properties of this schema.

A `dataClass` outside `public`, `internal` and `confidential` fails. A capability outside `http`, `identity`, `store` and `queue` fails. `container-app` is not a capability. ADR-0009 names `container-app-service` as the hosting module, not as a capability key. The capability written in the current manifests is `http`.

A `modules.hosting` value that is neither a `br/platform` pin nor a `br:ghcr.io/aeroflow-air/<module>:<major>.<minor>.<patch>` pin fails. A pin to any other registry fails, including `br:mcr.microsoft.com/...` and `br:ghcr.io/someone-else/...`. A leading `v` or a pre-release suffix fails. Any `modules` key other than `hosting` fails. `modules` with no `hosting` pin fails.

## Not in this schema

Capability-to-module mapping is not here. ADR-0009 leaves that open until the first module is published. This file does not say which capability a module implements.

`modules` is optional. ADR-0009 names it, and the example includes `modules.hosting`, but the same record says there is no `infra-platform` repo, so no module exists, and leaves the capability-to-module mapping open until the first module is published. The three `workload.yaml` files on `main` do not set `modules`: `template-dotnet-service`, `svc-flight-status` and `svc-gate-allocation`. Their headers say the hosting module is not published, so the file does not pin `br/platform`. Requiring `modules` would reject those files. This schema does not invent a pin to close that gap.

No identity, network or environment field is added. ADR-0009 does not name those as manifest keys.

## Tag to pin

The schema is versioned with this repo's release tags, the same tags as the workflows. It is not a separate package.

Once this is merged, consumers should pin the release tag that contains `schemas/workload.schema.json`. Do not pin `main`. The current tag `v0.1.0` does not contain this schema. This change does not create a tag.

## Check

The `lint` job in `.github/workflows/self-test.yml` runs `tests/workload-schema/validate.py`. `lint` is a required check on `main`. There is no second CI workflow.

`tests/workload-schema/valid/` holds copies of the three manifests, plus one synthetic file that sets `modules`. `tests/workload-schema/invalid/` must be rejected.

Copies of `workload.yaml` on `main`, taken 1 October 2026:

| Repo | Commit |
|------|--------|
| `template-dotnet-service` | `27cb3d6a239dde05abdd8775d73b379f20ca9f47` |
| `svc-flight-status` | `d44301a89c7d2702795cb5459c49f900b4760468` |
| `svc-gate-allocation` | `595efebdc50c3bca765d736b874657b86ee65b0e` |
