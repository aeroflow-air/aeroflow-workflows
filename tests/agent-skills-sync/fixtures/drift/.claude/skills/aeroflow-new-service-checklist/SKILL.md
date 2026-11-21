---
name: aeroflow-new-service-checklist
description: Checklist for creating a new AeroFlow svc-* repository from template-dotnet-service so it starts on the golden path (naming, manifest, CI pins, observability, domain shape, docs). Use when creating a new service or reviewing a freshly scaffolded one.
license: MIT
---

# New service checklist

## When to use
- Use this when creating `svc-<capability>` from the template, or reviewing one before its first feature PR.
- After that, use `aeroflow-add-endpoint`, `aeroflow-add-queue-consumer` and `aeroflow-add-otel-tracing`.

## Steps
1. **Name.** `svc-<business-capability>`, lowercase with hyphens, no tech in the name (`svc-booking`, not
   `svc-booking-api-dotnet`; ADR-0001). It's a public repo, one repo per service.
2. **Create from the template.** Use **Use this template** on template-dotnet-service. Rename
   `AeroFlow.ServiceTemplate` to `AeroFlow.<Capability>` everywhere: the `.sln`, folders, namespaces, the
   `Dockerfile` and tests.
3. **Manifest.** In `workload.yaml`, set `workload` and `repo` to the new name, `dataClass`
   (`public`/`internal`/`confidential`) and `capabilities` (`http`, `identity`, `store`, `queue`). Add `events:`
   if it uses Service Bus (ADR-0009, ADR-0019). Don't invent a `modules` pin. None is published.
4. **CI pins.** Workflows call `aeroflow-workflows` by tag, never `@main`. Move `ci.yml` to
   `dotnet-ci.yml@v0.6.0` and grant `packages: read` on the job. v0.6.0 requires it, and `github-packages: true`
   restores ServiceDefaults from the org feed. Keep explicit job-level `permissions`, because the org token is read-only.
5. **Observability.** Keep `AddServiceDefaults()` + `MapDefaultEndpoints()` and set `Observability:Squad`.
   Don't keep a second copy of the library. Follow `aeroflow-add-otel-tracing` for the package source.
6. **Replace the demo.** Delete `BookingsController`, `Models/` and `BookingLog`. Build a pure `Domain/`: static
   planner/lifecycle functions, `sealed record`s, value types with `Parse`, `Errors.cs`, and a small local
   `Result`/`Option` (BCL only, no LanguageExt). Edges go in `Controllers/`, `Messaging/` and `Storage/`. Copy gate-allocation's shape.
7. **Config.** Bind options with `AddOptions<XOptions>().BindConfiguration(XOptions.SectionName).ValidateDataAnnotations()
   .ValidateOnStart()`. Existing services use `Configure<T>(GetSection(...))` with no validation, so don't copy that.
8. **Events.** Publish only to `<capability>-events`, with canonical examples in `contracts/<topic>/`.
9. **Docs.** Write `docs/service.md` from the handbook's `templates/service-doc.md`, and rewrite the repo's agent
   file (`CLAUDE.md` today, `AGENTS.md` after the ADR-0023 rollout) for this service's domain and topics.
10. **Repo settings.** Protect `main` with the required check `build-and-test / build-and-test`, enforced for
   admins, and no force pushes. Add the service to the org profile README and, if it joins the event flow, to the airport overview.

## Example
- Template: [README](https://github.com/aeroflow-air/template-dotnet-service/blob/main/README.md), [Program.cs](https://github.com/aeroflow-air/template-dotnet-service/blob/main/src/AeroFlow.ServiceTemplate/Program.cs)
- Reference shape: [svc-gate-allocation Domain](https://github.com/aeroflow-air/svc-gate-allocation/tree/main/src/AeroFlow.GateAllocation/Domain)
- Manifest with events: [baggage-reclaim workload.yaml](https://github.com/aeroflow-air/svc-baggage-reclaim/blob/main/workload.yaml), [schema notes](https://github.com/aeroflow-air/aeroflow-workflows/blob/main/schemas/README.md)
- CI caller and pins: [dotnet-ci.yml](https://github.com/aeroflow-air/aeroflow-workflows/blob/main/.github/workflows/dotnet-ci.yml), [CHANGELOG](https://github.com/aeroflow-air/aeroflow-workflows/blob/main/CHANGELOG.md)
- Docs: [service docs standard](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/standards/service-docs.md), [service-doc template](https://github.com/aeroflow-air/platform-handbook/blob/main/templates/service-doc.md)
- Naming: [ADR-0001](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0001-repository-naming-convention.md), manifest: [ADR-0009](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0009-workload-manifest.md)
