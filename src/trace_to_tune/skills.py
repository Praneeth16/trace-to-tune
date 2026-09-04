from __future__ import annotations

import hashlib
import re
from pathlib import Path

from databricks.sdk import WorkspaceClient

SKILL_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def discover_skill_bundles(root: Path) -> dict[str, dict[str, bytes]]:
    bundles: dict[str, dict[str, bytes]] = {}
    if not root.is_dir():
        raise ValueError(f"Skills directory does not exist: {root}")

    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        name = skill_dir.name
        if not SKILL_NAME.fullmatch(name):
            raise ValueError(f"Invalid skill directory name: {name}")
        files = {
            str(path.relative_to(skill_dir)): path.read_bytes()
            for path in sorted(skill_dir.rglob("*"))
            if path.is_file() and not path.is_symlink()
        }
        if "SKILL.md" not in files:
            raise ValueError(f"Skill {name} is missing SKILL.md")
        bundles[name] = files
    if not bundles:
        raise ValueError(f"No skills found under {root}")
    return bundles


def load_governed_skill(
    workspace: WorkspaceClient, catalog: str, schema: str, skill: str
) -> tuple[str, str]:
    if not SKILL_NAME.fullmatch(skill):
        raise ValueError(f"Invalid skill name: {skill}")
    path = f"/Skills/{catalog}/{schema}/{skill}/SKILL.md"
    response = workspace.files.download(path)
    try:
        content = response.contents.read().decode("utf-8")
    finally:
        response.contents.close()
    if not content.strip():
        raise RuntimeError(f"Governed skill is empty: {path}")
    return content, hashlib.sha256(content.encode()).hexdigest()
