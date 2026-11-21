#!/usr/bin/env python3
"""Check or sync a repo's pinned agent skills (ADR-0023).

The repo pins a release of aeroflow-air/agent-skills in `.agent-skills.yaml`:

    source: aeroflow-air/agent-skills   # optional, this is the default
    version: v0.1.0                     # required, vMAJOR.MINOR.PATCH
    skills: default                     # optional: `default` (default-set.txt) or a list
    exclude: []                         # optional: platform skills this repo replaces

Only `aeroflow-*` folders under the skills directory are managed. Any other folder
(a squad's own skill) is never read, changed or deleted.

Commands (stdlib only, like validate-decisions.py):
    read  --config F                                  print source=/version= lines (for GITHUB_OUTPUT)
    check --config F --skills-dir D --source-dir S    exit 1 if managed folders drift from the pin
    sync  --config F --skills-dir D --source-dir S [--set-version vX.Y.Z]
                                                      make managed folders match S (optionally bump the pin)
Exit codes: 0 clean or synced, 1 drift, 2 bad config or source.
"""
from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

PREFIX = "aeroflow-"
DEFAULT_SOURCE = "aeroflow-air/agent-skills"
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
SOURCE_RE = re.compile(r"^aeroflow-air/[A-Za-z0-9._-]+$")
NAME_RE = re.compile(r"^aeroflow-[a-z0-9]+(-[a-z0-9]+)*$")
KEYS = {"source", "version", "skills", "exclude"}


class ConfigError(Exception):
    pass


@dataclass
class Pin:
    source: str
    version: str
    skills: str | list[str]
    exclude: list[str] = field(default_factory=list)


def _scalar(raw: str) -> str:
    value = raw.split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _inline_list(raw: str) -> list[str]:
    inner = raw.split(" #", 1)[0].strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise ConfigError(f"expected an inline list like [a, b], got: {raw.strip()}")
    return [_scalar(item) for item in inner[1:-1].split(",") if item.strip()]


def parse_pin(path: Path) -> Pin:
    """Parse the small YAML subset the pin file uses: scalars, inline lists, block lists, comments."""
    if not path.is_file():
        raise ConfigError(f"{path} not found")
    values: dict[str, str | list[str]] = {}
    current: str | None = None
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")) and stripped.startswith("- "):
            if current is None or not isinstance(values.get(current), list):
                raise ConfigError(f"{path}:{n}: list item without a list key")
            values[current].append(_scalar(stripped[2:]))  # type: ignore[union-attr]
            continue
        key, sep, rest = line.partition(":")
        key = key.strip()
        if not sep or line.startswith((" ", "\t")):
            raise ConfigError(f"{path}:{n}: expected `key: value`")
        if key not in KEYS:
            raise ConfigError(f"{path}:{n}: unknown key '{key}' (allowed: {', '.join(sorted(KEYS))})")
        if key in values:
            raise ConfigError(f"{path}:{n}: duplicate key '{key}'")
        rest = rest.strip()
        if rest.startswith("["):
            values[key] = _inline_list(rest)
        elif not _scalar(rest):
            values[key] = []
        else:
            values[key] = _scalar(rest)
        current = key

    source = values.get("source", DEFAULT_SOURCE)
    version = values.get("version")
    skills = values.get("skills", "default")
    exclude = values.get("exclude", [])
    if not isinstance(source, str) or not SOURCE_RE.match(source):
        raise ConfigError(f"source must be an aeroflow-air repository, got {source!r}")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise ConfigError(f"version must be a release tag like v0.1.0, got {version!r}")
    if isinstance(skills, str) and skills != "default":
        raise ConfigError("skills must be `default` or a list of skill names")
    if isinstance(skills, list) and not skills:
        raise ConfigError("skills list is empty; use `default` or name at least one skill")
    if not isinstance(exclude, list):
        raise ConfigError("exclude must be a list")
    for name in (skills if isinstance(skills, list) else []) + exclude:
        if not NAME_RE.match(name):
            raise ConfigError(f"'{name}' is not a platform skill name (aeroflow-*)")
    return Pin(source, version, skills, exclude)


def expected_skills(pin: Pin, source_dir: Path) -> list[str]:
    if pin.skills == "default":
        default_set = source_dir / "default-set.txt"
        if not default_set.is_file():
            raise ConfigError(f"{pin.source}@{pin.version} has no default-set.txt")
        names = [line.split("#", 1)[0].strip() for line in default_set.read_text(encoding="utf-8").splitlines()]
        names = [n for n in names if n]
    else:
        names = list(pin.skills)
    for name in pin.exclude:
        if name not in names:
            print(f"warning: exclude '{name}' is not in the selected set at {pin.version}", file=sys.stderr)
    selected = [n for n in names if n not in pin.exclude]
    for name in selected:
        if not NAME_RE.match(name) or not (source_dir / "skills" / name / "SKILL.md").is_file():
            raise ConfigError(f"skill '{name}' does not exist in {pin.source}@{pin.version}")
    return sorted(selected)


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def drift(pin: Pin, skills_dir: Path, source_dir: Path) -> list[str]:
    """Differences between the managed aeroflow-* folders and the pinned release."""
    expected = expected_skills(pin, source_dir)
    present = sorted(p.name for p in skills_dir.glob(f"{PREFIX}*")) if skills_dir.is_dir() else []
    problems: list[str] = []
    for name in present:
        if name not in expected:
            why = "excluded in .agent-skills.yaml" if name in pin.exclude else f"not in {pin.version}"
            problems.append(f"{name}: unexpected managed folder ({why}); squad-owned skills must not use the '{PREFIX}' prefix")
    for name in expected:
        theirs, ours = source_dir / "skills" / name, skills_dir / name
        if not ours.is_dir():
            problems.append(f"{name}: missing")
            continue
        want, have = _files(theirs), _files(ours)
        for rel in sorted(want - have):
            problems.append(f"{name}/{rel}: missing")
        for rel in sorted(have - want):
            problems.append(f"{name}/{rel}: not in {pin.version}")
        for rel in sorted(want & have):
            if not filecmp.cmp(theirs / rel, ours / rel, shallow=False):
                problems.append(f"{name}/{rel}: differs from {pin.version}")
    return problems


def sync(pin: Pin, skills_dir: Path, source_dir: Path) -> list[str]:
    expected = expected_skills(pin, source_dir)
    skills_dir.mkdir(parents=True, exist_ok=True)
    for managed in skills_dir.glob(f"{PREFIX}*"):
        if managed.is_dir():
            shutil.rmtree(managed)
        else:
            managed.unlink()
    for name in expected:
        shutil.copytree(source_dir / "skills" / name, skills_dir / name)
    return expected


def set_version(config: Path, version: str) -> None:
    if not VERSION_RE.match(version):
        raise ConfigError(f"--set-version must look like v0.1.0, got {version!r}")
    text = config.read_text(encoding="utf-8")
    new, count = re.subn(r"^(version:\s*)(\S+)", lambda m: m.group(1) + version, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise ConfigError(f"{config} has no `version:` line")
    config.write_text(new, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["read", "check", "sync"])
    parser.add_argument("--config", type=Path, default=Path(".agent-skills.yaml"))
    parser.add_argument("--skills-dir", type=Path, default=Path(".claude/skills"))
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--set-version")
    args = parser.parse_args(argv)
    try:
        pin = parse_pin(args.config)
        if args.command == "read":
            print(f"source={pin.source}")
            print(f"version={pin.version}")
            return 0
        if args.source_dir is None:
            raise ConfigError("--source-dir is required for check and sync")
        if args.command == "check":
            problems = drift(pin, args.skills_dir, args.source_dir)
            for p in problems:
                print(f"drift: {p}")
            print(f"{args.skills_dir}: {'in sync with' if not problems else f'{len(problems)} difference(s) from'} "
                  f"{pin.source}@{pin.version}")
            return 1 if problems else 0
        if args.set_version:
            set_version(args.config, args.set_version)
            pin = parse_pin(args.config)
        names = sync(pin, args.skills_dir, args.source_dir)
        print(f"{args.skills_dir}: synced {len(names)} skill(s) from {pin.source}@{pin.version}: {', '.join(names)}")
        return 0
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
