#!/usr/bin/env bash
# Parity check for generator/generate.cs (.NET 10 file-based app).
# Runs the C# generator through its CLI for every golden case in
# test_generate.py and requires byte-identical output, then checks that every
# invalid schema fixture and a few rule violations are refused (exit 1).
# Needs the .NET 10 SDK. Run from anywhere: tests/generator/run_csharp_golden.sh
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
gen=generator/generate.cs
here=tests/generator
# Two levels below the repo root, so --local-modules resolves to the golden
# files' ../../modules/container-app-service/main.bicep.
work="$root/.gen-csharp/out"
trap 'rm -rf "$root/.gen-csharp"' EXIT
fail=0

dotnet build "$gen" -v q -nologo >/dev/null
run() { dotnet run --no-build "$gen" -- "$@"; }

# manifest mode golden  (keep in sync with CASES in test_generate.py)
cases=(
  "svc-flight-status.yaml local svc-flight-status.local.bicep"
  "http-identity-pinned.yaml local http-identity-pinned.local.bicep"
  "http-identity-pinned.yaml registry http-identity-pinned.registry.bicep"
  "ghcr-pinned.yaml registry ghcr-pinned.registry.bicep"
  "svc-baggage-reclaim.yaml local svc-baggage-reclaim.local.bicep"
)
[ "$(ls "$here/golden" | wc -l)" -eq "${#cases[@]}" ] || { echo "FAIL golden file count differs from cases"; fail=1; }

for c in "${cases[@]}"; do
  read -r manifest mode golden <<<"$c"
  rm -rf "$work"
  args=(--manifest "$here/manifests/$manifest" --out-dir "$work")
  [ "$mode" = local ] && args+=(--local-modules modules)
  run "${args[@]}" >/dev/null
  if cmp -s "$work/main.bicep" "$here/golden/$golden"; then echo "ok   $golden"
  else echo "FAIL $golden"; diff -u "$here/golden/$golden" "$work/main.bicep" || true; fail=1; fi
done

expect_refused() { # file label
  rm -rf "$work"
  set +e; run --manifest "$1" --out-dir "$work" --local-modules modules >/dev/null 2>"$root/.gen-csharp/err"; code=$?; set -e
  if [ "$code" -eq 1 ] && [ ! -e "$work/main.bicep" ] && grep -q "${2:-}" "$root/.gen-csharp/err"; then echo "ok   refused $(basename "$1")"
  else echo "FAIL $(basename "$1") (exit $code)"; cat "$root/.gen-csharp/err"; fail=1; fi
}
mkdir -p "$root/.gen-csharp"
for f in tests/workload-schema/invalid/*.yaml; do expect_refused "$f" "does not match the schema"; done

rules="$root/.gen-csharp/rules"; mkdir -p "$rules"
hdr='repo: r
dataClass: internal'
printf 'workload: x1\n%s\ncapabilities: [http, queue]\n' "$hdr" >"$rules/queue-no-events.yaml"
printf 'workload: x1\n%s\ncapabilities: [http, store]\n' "$hdr" >"$rules/store.yaml"
printf 'workload: x1\n%s\ncapabilities: [identity]\n' "$hdr" >"$rules/no-http.yaml"
printf 'workload: Flight_Status\n%s\ncapabilities: [http]\n' "$hdr" >"$rules/bad-name.yaml"
printf 'workload: svc-baggage-reclaim\n%s\ncapabilities: [http, queue]\nevents:\n  publishes: [gate-events]\n' "$hdr" >"$rules/other-owner.yaml"
printf 'workload: x1\n%s\ncapabilities: [http]\nmodules:\n  hosting: br/platform:function-app:1.0.0\n' "$hdr" >"$rules/other-module.yaml"
expect_refused "$rules/queue-no-events.yaml" "queue needs an events: block"
expect_refused "$rules/store.yaml" "store is not yet supported"
expect_refused "$rules/no-http.yaml" "must include http"
expect_refused "$rules/bad-name.yaml" "cannot name a container app"
expect_refused "$rules/other-owner.yaml" "owned by svc-gate-allocation"
expect_refused "$rules/other-module.yaml" "not a container-app-service pin"

exit "$fail"
