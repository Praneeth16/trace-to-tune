from __future__ import annotations

import argparse
import json
from datetime import timedelta

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
    ServingModelWorkloadType,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument("--endpoint", default="trace-to-tune-skill-router")
    parser.add_argument(
        "--result",
        default="/Volumes/serverless_lakebase_praneeth_catalog/trace_to_tune/artifacts/latest_result.json",
    )
    args = parser.parse_args()

    workspace = WorkspaceClient(profile=args.profile)
    response = workspace.files.download(args.result)
    try:
        result = json.loads(response.contents.read())
    finally:
        response.contents.close()
    served_entity = ServedEntityInput(
        entity_name=result["registered_model"],
        entity_version=str(result["model_version"]),
        workload_type=ServingModelWorkloadType.GPU_MEDIUM,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )
    existing = {endpoint.name for endpoint in workspace.serving_endpoints.list()}
    config = EndpointCoreConfigInput(name=args.endpoint, served_entities=[served_entity])
    timeout = timedelta(minutes=45)
    if args.endpoint in existing:
        endpoint = workspace.serving_endpoints.get(args.endpoint)
        configurations = [endpoint.config, endpoint.pending_config]
        already_deploying = any(
            entity.entity_name == result["registered_model"]
            and str(entity.entity_version) == str(result["model_version"])
            for configuration in configurations
            if configuration
            for entity in configuration.served_entities or []
        )
        if already_deploying:
            workspace.serving_endpoints.wait_get_serving_endpoint_not_updating(
                args.endpoint, timeout=timeout
            )
        else:
            workspace.serving_endpoints.update_config_and_wait(
                name=args.endpoint,
                served_entities=[served_entity],
                timeout=timeout,
            )
    else:
        workspace.serving_endpoints.create_and_wait(
            name=args.endpoint,
            config=config,
            timeout=timeout,
        )
    print(
        json.dumps(
            {
                "endpoint": args.endpoint,
                "model": result["registered_model"],
                "version": result["model_version"],
            }
        )
    )


if __name__ == "__main__":
    main()
