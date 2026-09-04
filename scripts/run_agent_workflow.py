from __future__ import annotations

import argparse
import json
from pathlib import Path

import mlflow
from databricks.sdk import WorkspaceClient
from openai import OpenAI

from trace_to_tune.dataset import ROUTABLE_SKILLS, SYSTEM_PROMPT
from trace_to_tune.evaluate import parse_skill
from trace_to_tune.skills import load_governed_skill
from trace_to_tune.workflow import policy_decision, request_tags, require_safe_router_input


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument("--catalog", default="serverless_lakebase_praneeth_catalog")
    parser.add_argument("--schema", default="trace_to_tune")
    parser.add_argument("--router-endpoint", default="trace-to-tune-skill-router")
    parser.add_argument(
        "--model-service",
        default="serverless_lakebase_praneeth_catalog.trace_to_tune.governed_router",
    )
    parser.add_argument(
        "--prompt",
        default="Which delivery milestone has order DEMO-4821 reached?",
    )
    parser.add_argument("--output", default="outputs/runtime/agent-workflow.json")
    args = parser.parse_args()
    require_safe_router_input(args.prompt)

    workspace = WorkspaceClient(profile=args.profile)
    token = workspace.config.authenticate()["Authorization"].removeprefix("Bearer ")
    router_client = OpenAI(
        api_key=token,
        base_url=f"{workspace.config.host}/serving-endpoints",
    )
    gateway_client = OpenAI(
        api_key=token,
        base_url=f"{workspace.config.host}/ai-gateway/mlflow/v1",
    )

    current_user = workspace.current_user.me().user_name
    mlflow.set_tracking_uri(f"databricks://{args.profile}")
    mlflow.set_experiment(f"/Users/{current_user}/trace-to-tune-agent-workflow")

    with mlflow.start_span(name="trace-to-tune-agent", span_type="CHAIN") as root_span:
        root_span.set_inputs({"prompt": args.prompt})
        with mlflow.start_span(name="select-governed-skill", span_type="LLM") as route_span:
            route_span.set_inputs({"prompt": args.prompt, "endpoint": args.router_endpoint})
            route_response = router_client.chat.completions.create(
                model=args.router_endpoint,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": args.prompt},
                ],
                max_tokens=96,
                temperature=0,
            )
            route_content = route_response.choices[0].message.content or ""
            selected_skill = parse_skill(route_content)
            if selected_skill not in ROUTABLE_SKILLS:
                raise RuntimeError(f"Router returned an unknown skill: {route_content!r}")
            route_span.set_outputs(
                {"skill": selected_skill, "model": route_response.model}
            )

        with mlflow.start_span(name="load-governed-skill", span_type="TOOL") as skill_span:
            skill_path = f"/Skills/{args.catalog}/{args.schema}/{selected_skill}/SKILL.md"
            skill_span.set_inputs({"path": skill_path})
            governed_skill, skill_sha256 = load_governed_skill(
                workspace, args.catalog, args.schema, selected_skill
            )
            skill_span.set_outputs({"path": skill_path, "sha256": skill_sha256})

        tags = request_tags(selected_skill)
        with mlflow.start_span(name="governed-response", span_type="LLM") as response_span:
            response_span.set_inputs(
                {"prompt": args.prompt, "skill": selected_skill, "request_tags": tags}
            )
            gateway_response = gateway_client.chat.completions.with_raw_response.create(
                model=args.model_service,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Apply these governed skill instructions exactly. "
                            "Give a concise, privacy-safe next step.\n\n"
                            f"{governed_skill}"
                        ),
                    },
                    {"role": "user", "content": args.prompt},
                ],
                max_tokens=200,
                extra_headers={
                    "Databricks-Ai-Gateway-Request-Tags": json.dumps(tags)
                },
            )
            gateway_body = gateway_response.http_response.json()
            decision = policy_decision(gateway_body)
            response_span.set_outputs(
                {"policy_decision": decision, "response": gateway_body}
            )

        result = {
            "prompt": args.prompt,
            "selected_skill": selected_skill,
            "skill_version": tags["skill_version"],
            "skill_path": skill_path,
            "skill_sha256": skill_sha256,
            "policy_decision": decision,
            "router_endpoint": args.router_endpoint,
            "model_service": args.model_service,
            "gateway_status": gateway_response.http_response.status_code,
            "gateway_response": gateway_body,
            "mlflow_trace_id": root_span.trace_id,
        }
        root_span.set_outputs(result)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
