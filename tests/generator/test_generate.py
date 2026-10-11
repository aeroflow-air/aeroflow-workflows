"""Unit and golden-file tests for generator/generate.py.

Run: python -m unittest discover -s tests/generator -v
Refresh golden files after an intended change: UPDATE_GOLDEN=1 (then review the diff).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "generator"))

import generate as g  # noqa: E402

HERE = Path(__file__).resolve().parent
MANIFESTS = HERE / "manifests"
GOLDEN = HERE / "golden"
LOCAL_REF = "../../modules/container-app-service/main.bicep"

# (manifest, mode) -> golden file
CASES = {
    ("svc-flight-status.yaml", "local"): "svc-flight-status.local.bicep",
    ("http-identity-pinned.yaml", "local"): "http-identity-pinned.local.bicep",
    ("http-identity-pinned.yaml", "registry"): "http-identity-pinned.registry.bicep",
    ("ghcr-pinned.yaml", "registry"): "ghcr-pinned.registry.bicep",
}


def base(**overrides) -> dict:
    manifest = {"workload": "flight-status", "repo": "svc-flight-status", "dataClass": "internal", "capabilities": ["http"]}
    manifest.update(overrides)
    return manifest


class GoldenTests(unittest.TestCase):
    def test_golden_files(self):
        for (manifest, mode), golden in CASES.items():
            with self.subTest(manifest=manifest, mode=mode):
                data = g.load_manifest(MANIFESTS / manifest)
                actual = g.generate(data, LOCAL_REF if mode == "local" else None)
                path = GOLDEN / golden
                if os.environ.get("UPDATE_GOLDEN") == "1":
                    path.write_text(actual, encoding="utf-8")
                self.assertEqual(path.read_text(encoding="utf-8"), actual)

    def test_every_golden_file_has_a_case(self):
        self.assertEqual(sorted(p.name for p in GOLDEN.glob("*.bicep")), sorted(CASES.values()))


class GenerateTests(unittest.TestCase):
    def assertRefuses(self, manifest, fragment, ref=LOCAL_REF):
        with self.assertRaises(g.ManifestError) as ctx:
            g.generate(manifest, ref)
        self.assertIn(fragment, str(ctx.exception))

    def test_store_not_yet_supported(self):
        self.assertRefuses(base(capabilities=["http", "store"]), "store is not yet supported")

    def test_queue_not_yet_supported(self):
        self.assertRefuses(base(capabilities=["queue", "http"]), "queue is not yet supported")

    def test_identity_without_http_refused(self):
        self.assertRefuses(base(capabilities=["identity"]), "must include http")

    def test_empty_capabilities_refused(self):
        self.assertRefuses(base(capabilities=[]), "must include http")

    def test_registry_mode_needs_a_pin(self):
        self.assertRefuses(base(), "modules.hosting is not set", ref=None)

    def test_other_hosting_module_refused(self):
        self.assertRefuses(base(modules={"hosting": "br/platform:function-app:1.0.0"}), "not a container-app-service pin")

    def test_bad_container_app_name_refused(self):
        self.assertRefuses(base(workload="Flight_Status"), "cannot name a container app")
        self.assertRefuses(base(workload="a" * 29), "cannot name a container app")

    def test_registry_mode_uses_pin(self):
        out = g.generate(base(modules={"hosting": "br/platform:container-app-service:2.3.4"}))
        self.assertIn("module hosting 'br/platform:container-app-service:2.3.4'", out)

    def test_local_mode_overrides_pin(self):
        out = g.generate(base(modules={"hosting": "br/platform:container-app-service:2.3.4"}), LOCAL_REF)
        self.assertIn(f"module hosting '{LOCAL_REF}'", out)
        self.assertNotIn("br/platform:container-app-service:2.3.4'", out)

    def test_no_raw_resource_blocks(self):
        # ADR-0008/0009 done test: composition only, never a resource block.
        out = g.generate(base(capabilities=["http", "identity"]), LOCAL_REF)
        self.assertNotRegex(out, r"(?m)^\s*resource\s")


class ValidateTests(unittest.TestCase):
    def test_schema_errors_are_reported(self):
        with self.assertRaises(g.ManifestError) as ctx:
            g.validate(base(dataClass="secret", extra=1))
        message = str(ctx.exception)
        self.assertIn("dataClass", message)
        self.assertIn("extra", message)

    def test_schema_fixtures_agree(self):
        for path in sorted((ROOT / "tests" / "workload-schema" / "invalid").glob("*.yaml")):
            with self.subTest(path=path.name), self.assertRaises(g.ManifestError):
                g.load_manifest(path)


class CliTests(unittest.TestCase):
    def test_cli_local_modules_writes_buildable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            code = g.main(["--manifest", str(MANIFESTS / "svc-flight-status.yaml"), "--out-dir", str(out),
                           "--local-modules", str(ROOT / "modules")])
            self.assertEqual(code, 0)
            text = (out / "main.bicep").read_text(encoding="utf-8")
            ref = text.split("module hosting '")[1].split("'")[0]
            self.assertTrue((out / ref).resolve().is_file(), ref)

    def test_cli_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "workload.yaml"
            manifest.write_text("workload: x1\nrepo: r\ndataClass: internal\ncapabilities: [http, queue]\n", encoding="utf-8")
            self.assertEqual(g.main(["--manifest", str(manifest), "--out-dir", tmp, "--local-modules", str(ROOT / "modules")]), 1)
            self.assertFalse((Path(tmp) / "main.bicep").exists())


if __name__ == "__main__":
    unittest.main()
