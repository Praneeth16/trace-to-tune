from __future__ import annotations

import argparse
import json
from pathlib import Path

from databricks.sdk import WorkspaceClient
from openai import OpenAI


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument(
        "--service",
        default="serverless_lakebase_praneeth_catalog.trace_to_tune.governed_router",
    )
    parser.add_argument("--require-policy-block", action="store_true")
    parser.add_argument("--output", default="outputs/runtime/gateway-after-policy.json")
    args = parser.parse_args()

    workspace = WorkspaceClient(profile=args.profile)
    token = workspace.config.authenticate()["Authorization"].removeprefix("Bearer ")
    client = OpenAI(
        api_key=token,
        base_url=f"{workspace.config.host}/ai-gateway/mlflow/v1",
    )
    tests = [
        ("normal", "Choose the safest skill for checking order DEMO-2048."),
        ("pii", "Contact test.user@example.com and use demo PAN ABCDE1234F."),
    ]
    output = {}
    for name, prompt in tests:
        response = client.chat.completions.with_raw_response.create(
            model=args.service,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            extra_headers={
                "Databricks-Ai-Gateway-Request-Tags": json.dumps(
                    {"project": "trace-to-tune", "skill": "pii-safe-response", "test": name}
                )
            },
        )
        # Unity Gateway policy decisions live in the raw response extension.
        # The OpenAI model parser intentionally drops unknown Databricks fields.
        body = response.http_response.json()
        output[name] = {"status_code": response.http_response.status_code, "body": body}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, default=str) + "\n")
    print(json.dumps(output, indent=2, default=str))
    if args.require_policy_block:
        body = output["pii"]["body"]
        policy = body.get("databricks_service_policy", {})
        finish_reason = body.get("choices", [{}])[0].get("finish_reason")
        if policy.get("action") != "deny" or finish_reason != "content_filter":
            raise SystemExit(
                "Expected policy action='deny' and finish_reason='content_filter', "
                f"got policy={policy!r}, finish_reason={finish_reason!r}"
            )


if __name__ == "__main__":
    main()
