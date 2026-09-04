import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from trace_to_tune.dataset import ROUTABLE_SKILLS
from trace_to_tune.skills import discover_skill_bundles, load_governed_skill


def test_governed_skill_bundles_cover_every_router_label() -> None:
    bundles = discover_skill_bundles(Path("skills"))
    assert set(ROUTABLE_SKILLS).issubset(bundles)
    assert set(bundles) == {*ROUTABLE_SKILLS, "trace-curation"}


def test_skill_bundle_requires_skill_markdown(tmp_path: Path) -> None:
    (tmp_path / "incomplete").mkdir()
    with pytest.raises(ValueError, match="missing SKILL.md"):
        discover_skill_bundles(tmp_path)


def test_governed_skill_loader_reads_the_published_file() -> None:
    content = b"# Order status\n\nRead only.\n"
    downloaded = []

    class Files:
        def download(self, path: str):
            downloaded.append(path)
            return SimpleNamespace(contents=BytesIO(content))

    workspace = SimpleNamespace(files=Files())
    text, digest = load_governed_skill(workspace, "catalog", "schema", "order-status")

    assert downloaded == ["/Skills/catalog/schema/order-status/SKILL.md"]
    assert text == content.decode()
    assert digest == hashlib.sha256(content).hexdigest()
