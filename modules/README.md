# Local module stand-ins

`container-app-service/main.bicep` is a verbatim copy of the module source in
[`infra-platform`](https://github.com/aeroflow-air/infra-platform/tree/main/modules/container-app-service)
at commit `5097465`, with a provenance header added.

No `br/platform` module is published yet, and publishing to Azure Container
Registry would cost money, so CI cannot restore the real module. The generator's
`--local-modules` mode swaps the registry reference for a relative path to this
folder so `bicep build` and `bicep lint` can compile the generated composition
without Azure.

Mapping to the registry later:

| Mode | Module reference in generated Bicep |
| --- | --- |
| `--local-modules modules` (CI today) | `'../.../modules/container-app-service/main.bicep'` |
| registry (default) | the manifest's `modules.hosting` pin, for example `'br/platform:container-app-service:0.1.0'` |

Once `infra-platform` publishes a version (GHCR `br:ghcr.io/aeroflow-air/...` or
the `br/platform` alias), service manifests add `modules.hosting`, the workflow
drops `--local-modules`, and this folder is deleted. Only the module name
`container-app-service` has a stand-in; the generator refuses any other.
