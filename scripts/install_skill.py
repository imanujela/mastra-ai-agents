"""Install the bundled skill pack into a Hermes skills tree.

Run: python scripts/install_skill.py [--hermes-home PATH] [--dry-run] [--force]

The copy is transactional: the existing skill is moved aside as
``<name>.bak-<timestamp>`` first, and restored if the copy fails. Nothing is
written to the home directory unless ``--hermes-home`` or ``HERMES_HOME`` says so.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

SKILL_NAME = "mastra-orchestration"
CATEGORY = "autonomous-ai-agents"


def hermes_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if os.environ.get("HERMES_HOME"):
        return Path(os.environ["HERMES_HOME"]).expanduser()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "hermes"
    return Path.home() / ".local" / "share" / "hermes"


def repo_skill_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "skills" / SKILL_NAME


def copy_skill(source: Path, target: Path) -> list[str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if target.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = target.with_name(f"{target.name}.bak-{stamp}")
        target.rename(backup)
    try:
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    except Exception:
        if backup is not None and backup.exists():
            shutil.rmtree(target, ignore_errors=True)
            backup.rename(target)
        raise
    written = sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="install_skill")
    parser.add_argument("--hermes-home")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    source = repo_skill_dir()
    if not (source / "SKILL.md").is_file():
        print(json.dumps({"error": f"missing skill source: {source}"}))
        return 2

    target = hermes_home(args.hermes_home) / "skills" / CATEGORY / SKILL_NAME
    if target.exists() and not args.force and not args.dry_run:
        print(
            json.dumps(
                {
                    "error": "skill already installed",
                    "target": str(target),
                    "hint": "pass --force to replace it (the old copy is kept as a .bak-<utc> sibling)",
                }
            )
        )
        return 2

    if args.dry_run:
        print(json.dumps({"dry_run": True, "source": str(source), "target": str(target)}))
        return 0

    written = copy_skill(source, target)
    print(json.dumps({"installed": True, "target": str(target), "files": written}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
