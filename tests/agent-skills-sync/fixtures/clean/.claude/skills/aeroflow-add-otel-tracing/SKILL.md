---
name: aeroflow-add-otel-tracing
description: Give an AeroFlow service golden-path observability (traces, metrics, structured logs, health) through AeroFlow.ServiceDefaults, then add business events or custom spans. Use when wiring telemetry into a service, adding a log line or span, or writing observability tests.
license: MIT
---

# Add observability (OpenTelemetry) the AeroFlow way

## When to use
- When a service doesn't call `AddServiceDefaults()` yet, or you want a business log, a custom span or a health check.
- Squads don't wire exporters, metric names or sampling themselves (ADR-0022).

## Steps
1. **Reference the package from the org feed.** Add a `nuget.config` source
   `https://nuget.pkg.github.com/aeroflow-air/index.json` (no token in the file) and
   `<PackageReference Include="AeroFlow.ServiceDefaults" Version="0.1.0" />`. Test projects also reference
   `AeroFlow.ServiceDefaults.Testing`. CI calls `dotnet-ci.yml@v0.6.0` with `github-packages: true` and the job
   grants `packages: read`. v0.6.0 needs `packages: read` even if the feed input is off.
   Today the svc-* repos still restore from a committed `lib/packages` feed, and the template uses a project reference,
   until the feed switch PRs land. `docker build` against the feed still needs a token build secret, which isn't solved yet.
2. **Two calls in `Program.cs`.** Call `builder.AddServiceDefaults();` before `Build()` and
   `app.MapDefaultEndpoints();` after. That gives OTel traces, metrics and logs, HTTP request logs (1000/1001/1002),
   `/health` (readiness) and `/alive` (liveness), both anonymous and kept out of traces and logs.
3. **Configure, don't code.** Set `Observability:Squad` (and optionally `ServiceName`, `ServiceVersion`,
   `Environment`). Exporters switch on from `OTEL_EXPORTER_OTLP_ENDPOINT` (the Aspire dashboard) or
   `APPLICATIONINSIGHTS_CONNECTION_STRING`. Don't add exporters in code.
4. **Business events.** Use source-generated `[LoggerMessage]` in a `static partial` class next to the edge,
   with a fixed `EventId` of 10,000 or above, a constant template and named properties. CA1848, CA2254 and RS0030
   (`Console`, `Debug.WriteLine` banned) are build errors. Never log from `Domain/`, and no PII, secrets or bodies.
5. **Messaging and edge failures.** Inject `IObservabilityLog` and call `MessagePublished`, `MessageConsumed` or
   `OperationFailed` (2000–2003, 3000) instead of writing your own lines.
6. **Custom spans (rarely needed).** Inject `ObservabilityResource` and create
   `new ActivitySource(resource.ServiceName)`. Only that source name is exported. Then `StartActivity(...)`, and
   put the flight id on the span with `FlightId.Set(activity, id)`. Flight id goes on spans and logs, never as a metric dimension.
7. **Readiness checks.** Register a dependency check with `AddHealthChecks().AddCheck(...)` **without** the
   `live` tag, so it affects `/health` only. No service does this yet (ADR-0023 gap).
8. **Contract test.** Register a `LogCollector` as the `ILoggerProvider` in `WebApplicationFactory` and call an
   endpoint, then assert with `RequireHttpRequest(...)`, `RequireRequiredFields(...)` and `RequireFlightId(...)`.
   Keep the health tests.
9. **Docs.** List the new event ids and their log signatures under failure modes in `docs/service.md`.

## Example
- Package: [Extensions.cs](https://github.com/aeroflow-air/lib-service-defaults/blob/main/src/AeroFlow.ServiceDefaults/Extensions.cs), [event catalogue](https://github.com/aeroflow-air/lib-service-defaults/blob/main/docs/service-defaults.md), [consume and auth](https://github.com/aeroflow-air/lib-service-defaults/blob/main/README.md)
- Wiring: [template Program.cs](https://github.com/aeroflow-air/template-dotnet-service/blob/main/src/AeroFlow.ServiceTemplate/Program.cs)
- Business events: [BookingLog.cs](https://github.com/aeroflow-air/template-dotnet-service/blob/main/src/AeroFlow.ServiceTemplate/BookingLog.cs), [OutboxDispatcher.cs](https://github.com/aeroflow-air/svc-baggage-reclaim/blob/main/src/AeroFlow.BaggageReclaim/Messaging/OutboxDispatcher.cs)
- Custom span: [FlightSimulatorWorker.cs](https://github.com/aeroflow-air/aeroflow-local/blob/main/src/AeroFlow.Local.FlightSimulator/FlightSimulatorWorker.cs) (it predates the package)
- Tests: [ObservabilityContractTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/ObservabilityContractTests.cs), [HealthEndpointTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/HealthEndpointTests.cs)
- Rules: [ADR-0022](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0022-observability-on-the-golden-path.md). W3C context over Service Bus has not landed yet.
