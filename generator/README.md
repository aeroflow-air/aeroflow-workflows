# Workload generator

`generate.py` turns a service's `workload.yaml` into `main.bicep` (ADR-0009). The output is not committed to the service repo.

```bash
python3 -m venv .venv && .venv/bin/pip install 'jsonschema==4.23.0' 'PyYAML==6.0.2'
.venv/bin/python generator/generate.py --manifest ../svc-flight-status/workload.yaml --out-dir out --local-modules modules
bicep build out/main.bicep
```

## C# version (generate.cs)

`generate.cs` is a line-for-line port of `generate.py` as a [.NET 10 file-based app](https://learn.microsoft.com/dotnet/core/sdk/file-based-apps): one `.cs` file, no `.csproj`. Its NuGet packages (YamlDotNet, JsonSchema.Net) are declared with `#:package` directives at the top of the file. It needs the **.NET 10 SDK** (not just the runtime).

```bash
dotnet run generator/generate.cs -- --manifest ../svc-flight-status/workload.yaml --out-dir out --local-modules modules
# or, on Linux/macOS: chmod +x generator/generate.cs && ./generator/generate.cs --manifest ...
tests/generator/run_csharp_golden.sh   # byte-identical check against tests/generator/golden
```

Same CLI, same schema file, same rules and messages, same output. The first run restores and builds (a few seconds); later runs reuse the SDK's build cache. Schema-error wording differs, because it comes from JsonSchema.Net instead of Python's `jsonschema`; the failing paths and the exit code (1) are the same. `workload-deploy.yml` runs Python by default; callers can opt in with `generator: csharp`. If it outgrows one file, `dotnet project convert generator/generate.cs` turns it into a normal project.

## Why Python

The repo already validates the schema with Python, `jsonschema` 4.23.0 and PyYAML 6.0.2 (see `self-test.yml`), so the generator reuses the same pinned dependencies and the same validator as the `lint` check. Python is on every GitHub runner, so there is no build step, and tests use the standard library's `unittest`. A .NET console app would add a project, a build and a second YAML/JSON Schema stack for a ~150-line text template.

## Mapping

| Capability | Module | Notes |
| --- | --- | --- |
| `http` | `container-app-service` | Required. One container app, ingress `internal` by default. |
| `identity` | `container-app-service` | The module's system-assigned managed identity. No extra module. |
| `queue` | existing platform Service Bus namespace | Needs an `events:` block (ADR-0019): the generator references the platform-created topics/subscriptions as `existing` and emits role assignments — Sender (`69a216fc-…`) on the workload's own topic only, Receiver (`4f6d3b9b-…`) only on its own subscriptions, scoped to `hosting.outputs.principalId`. Publishing to another owner's topic (including `flight-events`, owned by the flight simulator) is refused. |
| `store` | none | Fails with "not yet supported" until a module and ADR exist. |

The module reference is the manifest's `modules.hosting` pin, or with `--local-modules DIR` a relative path to `DIR/container-app-service/main.bicep`. Without either, the generator fails, because no version is published. Only `container-app-service` is accepted as the hosting module.

The generated file declares `location` (defaults to the resource group), `containerImage` (from the future deploy step) and `ingress` (`internal` by default). The hosting part is module-only; an `events:` composition additionally contains `existing` Service Bus references and `roleAssignments` resources (never topic or subscription creation).

## Tests

```bash
.venv/bin/python -m unittest discover -s tests/generator -v
UPDATE_GOLDEN=1 .venv/bin/python -m unittest discover -s tests/generator   # refresh golden files, then review the diff
```

Golden files are in `tests/generator/golden/`. `tests/generator/run_csharp_golden.sh` checks the C# port against the same files (refresh them with Python, then rerun it).
