from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from openai import OpenAI

from trace_to_tune.gateway_contract import PROBES, validation_errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument(
        "--service",
        default="serverless_lakebase_praneeth_catalog.trace_to_tune.governed_router",
    )
    parser.add_argument("--require-policy-block", action="store_true")
    parser.add_argument("--output", default="outputs/runtime/gateway-policy-results.json")
    args = parser.parse_args()

    workspace = WorkspaceClient(profile=args.profile)
    token = workspace.config.authenticate()["Authorization"].removeprefix("Bearer ")
    client = OpenAI(
        api_key=token,
        base_url=f"{workspace.config.host}/ai-gateway/mlflow/v1",
    )
    output: dict[str, object] = {}
    for probe in PROBES:
        response = client.chat.completions.with_raw_response.create(
            model=args.service,
            messages=[{"role": "user", "content": probe.prompt}],
            max_tokens=300,
            extra_headers={
                "Databricks-Ai-Gateway-Request-Tags": json.dumps(probe.request_tags)
            },
        )
        body = response.http_response.json()
        output[probe.name] = {
            "status_code": response.http_response.status_code,
            "request_tags": probe.request_tags,
            "body": body,
        }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str) + "\n")
    print(json.dumps(output, indent=2, default=str))

    errors = validation_errors(output, args.require_policy_block)
    if errors:
        raise SystemExit("Gateway verification failed: " + "; ".join(errors))


if __name__ == "__main__":
    main()
