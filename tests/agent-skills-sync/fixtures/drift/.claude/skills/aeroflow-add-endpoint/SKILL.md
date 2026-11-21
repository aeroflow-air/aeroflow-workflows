---
name: aeroflow-add-endpoint
description: Add an HTTP endpoint to an AeroFlow .NET service as a controller action over pure domain functions, with typed errors returned as ProblemDetails. Use when adding or changing an API route in a svc-* repo or the service template.
license: MIT
---

# Add an HTTP endpoint

## When to use
- Use this for a new route, or a change to a route's request, response or status codes, in a `svc-*` repo.
- Don't use it for event handling. That's `aeroflow-add-queue-consumer`.

## Steps
1. **Controllers, not minimal APIs.** Add an action to a `[ApiController]` class in `Controllers/`
   (`public sealed class XController(IStore store) : ControllerBase`). No `MapGet` / `MapPost`.
2. **Wire records.** Put request and response records in `Models/`. Nullable fields are allowed only here.
   The request gets a `ToCommand()` that returns `Result<TCommand>` by `Parse`-ing value types,
   so `null` never reaches `Domain/`.
3. **Domain stays pure.** The rule goes in a static function in `Domain/` that returns `Result<T>`. That
   means no I/O, no logging, no `DateTimeOffset.UtcNow` (pass a value from `TimeProvider`) and no throwing
   for business rules. A new failure gets a typed error record in `Domain/Errors.cs` that derives from
   `ValidationError` (400), `NotFoundError` (404) or `RuleViolation` (409), with a stable snake_case `code`.
4. **Compose and match.** `Parse(...).Bind(...).Match<ActionResult>(ok => Ok(...), this.Problem)`.
   Writes go through the store's atomic `Update`. A lookup that finds nothing returns `Option<T>` and uses
   `.ToResult(() => new XNotFound(...))`.
5. **ProblemDetails, one way.** Errors go out through `this.Problem(error)` from `Controllers/ProblemResults.cs`
   (status from the error family, `code` extension). Copy gate-allocation's file. Don't copy flight-status's
   inline version in `FlightsController`. That's the odd one out (ADR-0023).
6. **Document it.** Add XML `<summary>` / `<response>` comments and `[ProducesResponseType]` for each status,
   with `typeof(ProblemDetails)` for errors. OpenAPI/Scalar picks these up when `ApiDocs:Enabled` (ADR-0015).
7. **Auth for writes.** Add `[Authorize(Policy = ...)]` at the edge only (ADR-0018). The domain never sees callers.
8. **Business log, if useful.** Use a `[LoggerMessage]` method with an id of 10,000 or above, next to the
   controller. Request logs are automatic (ServiceDefaults event 1000/1001).
9. **Test.** Write API tests with `WebApplicationFactory<Program>` and `FakeTimeProvider`. Assert the status
   and the ProblemDetails `code` for each failure, and keep domain tests free of mocks.
10. **Docs.** Update `docs/service.md` (inputs, outputs, failure modes) in the same PR.

## Example
- Controller: [AllocationsController.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Controllers/AllocationsController.cs)
- Error mapping to follow: [ProblemResults.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Controllers/ProblemResults.cs)
- Request to command: [Requests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Models/Requests.cs)
- Typed errors: [Errors.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Domain/Errors.cs)
- Write with an auth policy: [ReclaimController.cs](https://github.com/aeroflow-air/svc-baggage-reclaim/blob/main/src/AeroFlow.BaggageReclaim/Controllers/ReclaimController.cs)
- API tests (`AssertProblem`): [GateAllocationApiTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/Api/GateAllocationApiTests.cs)
- Rules: [coding standards](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/standards/coding-standards.md), [ADR-0004](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0004-functional-style-csharp.md)
Local edit that should have gone upstream.
