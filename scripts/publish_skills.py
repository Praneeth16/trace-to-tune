from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import AlreadyExists

from trace_to_tune.skills import discover_skill_bundles

SKILLS_API = "/api/2.1/unity-catalog/skills"
FILES_API = "/api/2.0/fs/files"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument("--catalog", default="serverless_lakebase_praneeth_catalog")
    parser.add_argument("--schema", default="trace_to_tune")
    parser.add_argument("--skills-dir", type=Path, default=Path("skills"))
    args = parser.parse_args()

    workspace = WorkspaceClient(profile=args.profile)
    api = workspace.api_client
    bundles = discover_skill_bundles(args.skills_dir)
    results = []
    for name, files in bundles.items():
        try:
            api.do(
                "POST",
                SKILLS_API,
                query={"parent": f"schemas/{args.catalog}.{args.schema}", "skill_id": name},
                body={},
            )
            action = "created"
        except AlreadyExists:
            action = "updated"

        for relative_path, content in files.items():
            api.do(
                "PUT",
                f"{FILES_API}/Skills/{args.catalog}/{args.schema}/{name}/{relative_path}",
                headers={"Content-Type": "application/octet-stream"},
                data=content,
            )
        api.do("POST", f"{SKILLS_API}/{args.catalog}.{args.schema}.{name}/finalize")
        results.append({"skill": name, "action": action, "files": len(files)})

    print(json.dumps({"published": results}, indent=2))


if __name__ == "__main__":
    main()
