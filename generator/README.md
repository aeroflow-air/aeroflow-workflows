# Workload generator

`generate.py` turns a service's `workload.yaml` into `main.bicep` (ADR-0009). The output is not committed to the service repo.

```bash
python3 -m venv .venv && .venv/bin/pip install 'jsonschema==4.23.0' 'PyYAML==6.0.2'
.venv/bin/python generator/generate.py --manifest ../svc-flight-status/workload.yaml --out-dir out --local-modules modules
bicep build out/main.bicep
```

## Why Python

The repo already validates the schema with Python, `jsonschema` 4.23.0 and PyYAML 6.0.2 (see `self-test.yml`), so the generator reuses the same pinned dependencies and the same validator as the `lint` check. Python is on every GitHub runner, so there is no build step, and tests use the standard library's `unittest`. A .NET console app would add a project, a build and a second YAML/JSON Schema stack for a ~150-line text template.

## Mapping

| Capability | Module | Notes |
| --- | --- | --- |
| `http` | `container-app-service` | Required. One container app, ingress `internal` by default. |
| `identity` | `container-app-service` | The module's system-assigned managed identity. No extra module. |
| `store`, `queue` | none | Fail with "not yet supported" until a module and ADR exist. |

The module reference is the manifest's `modules.hosting` pin, or with `--local-modules DIR` a relative path to `DIR/container-app-service/main.bicep`. Without either, the generator fails, because no version is published. Only `container-app-service` is accepted as the hosting module.

The generated file declares `location` (defaults to the resource group), `containerImage` (from the future deploy step) and `ingress` (`internal` by default). It never contains a `resource` block.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests/generator -v
UPDATE_GOLDEN=1 .venv/bin/python -m unittest discover -s tests/generator   # refresh golden files, then review the diff
```

Golden files are in `tests/generator/golden/`.
