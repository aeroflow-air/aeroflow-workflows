---
name: aeroflow-add-queue-consumer
description: Subscribe an AeroFlow service to another squad's Service Bus topic with an idempotent handler, outbox publishing and contract tests. Use when a service must react to events such as flight-events, or publish its own events as a result.
license: MIT
---

# Add a queue consumer

## When to use
- A service reacts to another topic (`flight-events`, `gate-events`, ...), or a handler publishes events.
- A service only ever subscribes to other squads' topics. It publishes only to its own
  `<capability>-events` (ADR-0013, ADR-0019).

## Steps
1. **Declare it.** In `workload.yaml`, set `capabilities: [http, queue]` and add an `events:` block
   (`publishes`, `subscribes` with `topic` and `subscription`). Follow baggage-reclaim. gate-allocation
   consumes and publishes too but hasn't declared it yet (gap).
2. **Pin the contract.** Copy the producer's canonical examples into `tests/<Project>.Tests/Contracts/<topic>/`
   (consumer-owned copies, ADR-0019). Never edit a pinned copy to make a test pass.
3. **Wire message and options.** A `<Topic>Message` record (nullable fields allowed) and `<Topic>Options` with
   a `SectionName`, `Topic` and `Subscription`. Start the processor only when `ConnectionStrings:messaging` is set.
4. **Processor (edge).** An `IHostedService` with `AutoCompleteMessages = false`. A body that won't
   deserialise (including an unknown event type) goes to dead-letter with reason `unreadable`.
   Everything else is handled and then completed.
5. **Handler returns an outcome, never throws.** `Applied`, `Ignored(reason)` or `Rejected(error)`.
   Late, out-of-order or irrelevant events are `Ignored` or `Rejected` with a reason. Business rules
   stay in pure `Domain/` functions that return `Result<T>`.
6. **Idempotent by event id.** Check `HasProcessed(eventId)` and record the id in the same atomic store
   update as the change, so a redelivery is `Ignored`.
7. **Publish through the outbox only (ADR-0017).** Save the change and its outgoing events in one store
   update, and let `OutboxDispatcher` send them. Event ids come from `EventIds.Derive(sourceEventId, type)`
   (never `Guid.NewGuid`). Set MessageId = event id, Subject = event type, CorrelationId = flight id.
8. **Platform logs.** Call `IObservabilityLog.MessageConsumed(..., MessageOutcomes.X, flightId)` for every
   outcome (event 2002), and `MessagePublished` / `MessagePublishFailed` in the publisher (2000/2001).
   Your own `[LoggerMessage]` lines use ids of 10,000 or above.
9. **Test.** Cover the handler (applied, ignored, rejected, duplicate delivery), the outbox (redelivery queues
   nothing new) and contract tests (every pinned example deserialises; an unknown type fails).
10. **Docs.** Update `docs/service.md` with the topic, subscription, outcomes and dead-letter reasons.

## Example
- Processor: [FlightEventsProcessor.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Messaging/FlightEventsProcessor.cs)
- Handler and outcomes: [GateEventHandler.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Messaging/GateEventHandler.cs)
- Outbox: [OutboxDispatcher.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Messaging/OutboxDispatcher.cs), ids: [EventIds.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/src/AeroFlow.GateAllocation/Domain/EventIds.cs)
- Manifest to follow: [baggage-reclaim workload.yaml](https://github.com/aeroflow-air/svc-baggage-reclaim/blob/main/workload.yaml)
- Tests: [GateEventHandlerTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/Messaging/GateEventHandlerTests.cs), [OutboxTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/Messaging/OutboxTests.cs), [FlightEventContractTests.cs](https://github.com/aeroflow-air/svc-gate-allocation/blob/main/tests/AeroFlow.GateAllocation.Tests/Messaging/FlightEventContractTests.cs)
- Pinned copies: [Contracts/flight-events](https://github.com/aeroflow-air/svc-gate-allocation/tree/main/tests/AeroFlow.GateAllocation.Tests/Contracts/flight-events)
- Rules: [ADR-0017](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0017-reliable-event-publishing.md), [ADR-0019](https://github.com/aeroflow-air/platform-handbook/blob/main/docs/decisions/0019-event-contracts-and-topic-ownership.md)
