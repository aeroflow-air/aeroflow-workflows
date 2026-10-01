#!/usr/bin/env python3
"""Validate workload manifests against schemas/workload.schema.json.

Fixtures under tests/workload-schema/valid must pass. Fixtures under
tests/workload-schema/invalid must fail. Extra YAML paths on the command
line must pass. Used by the lint job in .github/workflows/self-test.yml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "workload.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    failed = False
    valid_dir = root / "tests" / "workload-schema" / "valid"
    invalid_dir = root / "tests" / "workload-schema" / "invalid"

    for path in sorted(valid_dir.glob("*.yaml")):
        failed = report_must_pass(validator, path) or failed

    for path in sorted(invalid_dir.glob("*.yaml")):
        failed = report_must_fail(validator, path) or failed

    for arg in sys.argv[1:]:
        failed = report_must_pass(validator, Path(arg)) or failed

    return 1 if failed else 0


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def report_must_pass(validator: Draft202012Validator, path: Path) -> bool:
    errors = sorted(validator.iter_errors(load_yaml(path)), key=lambda e: list(e.absolute_path))
    if errors:
        print(f"FAIL {path} (expected valid)")
        for error in errors:
            loc = "/".join(str(part) for part in error.absolute_path) or "(root)"
            print(f"  {loc}: {error.message}")
        return True
    print(f"ok   {path}")
    return False


def report_must_fail(validator: Draft202012Validator, path: Path) -> bool:
    errors = list(validator.iter_errors(load_yaml(path)))
    if not errors:
        print(f"FAIL {path} (expected invalid, but it passed)")
        return True
    print(f"ok   {path} rejected ({len(errors)} error(s))")
    return False


if __name__ == "__main__":
    sys.exit(main())
