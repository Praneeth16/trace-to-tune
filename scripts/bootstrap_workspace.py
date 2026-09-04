from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient

from trace_to_tune.dataset import generate_trace_rows


def cli(profile: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["databricks", *args, "--profile", profile, "-o", "json"],
        check=check,
        capture_output=True,
        text=True,
    )


def execute_sql(client: WorkspaceClient, warehouse_id: str, statement: str) -> None:
    response = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="50s",
    )
    if response.status and response.status.error:
        raise RuntimeError(response.status.error.message)


def seed_unity_catalog(
    client: WorkspaceClient, warehouse_id: str, catalog: str, schema: str
) -> None:
    execute_sql(client, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    execute_sql(
        client,
        warehouse_id,
        f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.artifacts COMMENT 'Trace-to-tune model artifacts and run evidence'",
    )
    execute_sql(
        client,
        warehouse_id,
        f"""
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.curated_traces (
          trace_id STRING, prompt STRING, completion STRING, skill_name STRING,
          skill_version STRING, split STRING, approved BOOLEAN, policy_decision STRING,
          curated_at TIMESTAMP
        ) USING DELTA
        """,
    )
    execute_sql(client, warehouse_id, f"TRUNCATE TABLE {catalog}.{schema}.curated_traces")
    values = []
    for row in generate_trace_rows():
        escaped = [
            str(row[key]).replace("'", "''")
            for key in (
                "trace_id",
                "prompt",
                "completion",
                "skill_name",
                "skill_version",
                "split",
                "policy_decision",
            )
        ]
        values.append(
            "("
            + ",".join(f"'{value}'" for value in escaped[:6])
            + ",TRUE,"
            + f"'{escaped[6]}',CURRENT_TIMESTAMP())"
        )
    execute_sql(
        client,
        warehouse_id,
        f"INSERT INTO {catalog}.{schema}.curated_traces VALUES " + ",".join(values),
    )


def seed_lakebase(profile: str, project: str) -> None:
    result = cli(profile, "postgres", "get-project", f"projects/{project}", check=False)
    if result.returncode != 0:
        cli(
            profile,
            "postgres",
            "create-project",
            project,
            "--json",
            json.dumps(
                {
                    "spec": {
                        "display_name": "Trace to Tune",
                        "default_endpoint_settings": {
                            "autoscaling_limit_min_cu": 0.5,
                            "autoscaling_limit_max_cu": 2,
                            "suspend_timeout_duration": "300s",
                        },
                    }
                }
            ),
        )

    endpoints = []
    for _ in range(30):
        payload = cli(
            profile,
            "postgres",
            "list-endpoints",
            f"projects/{project}/branches/production",
        ).stdout
        endpoints = json.loads(payload)
        if endpoints and endpoints[0].get("status", {}).get("current_state") == "ACTIVE":
            break
        time.sleep(5)
    if not endpoints:
        raise RuntimeError("Lakebase endpoint was not created")
    endpoint = endpoints[0]
    endpoint_name = endpoint["name"]
    host = endpoint["status"]["hosts"]["host"]
    token = json.loads(
        cli(profile, "postgres", "generate-database-credential", endpoint_name).stdout
    )["token"]
    user = json.loads(cli(profile, "current-user", "me").stdout)["userName"]

    admin_dsn = (
        f"host={host} port=5432 dbname=postgres user={user} password={token} sslmode=require"
    )
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'trace_to_tune'"
        ).fetchone()
        if not exists:
            connection.execute("CREATE DATABASE trace_to_tune")

    app_dsn = (
        f"host={host} port=5432 dbname=trace_to_tune user={user} password={token} sslmode=require"
    )
    with psycopg.connect(app_dsn) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_feedback (
              trace_id TEXT PRIMARY KEY,
              skill_name TEXT NOT NULL,
              reviewer_outcome TEXT NOT NULL,
              policy_decision TEXT NOT NULL,
              approved_for_training BOOLEAN NOT NULL,
              reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for row in generate_trace_rows():
            connection.execute(
                """
                INSERT INTO trace_feedback
                  (trace_id, skill_name, reviewer_outcome, policy_decision, approved_for_training)
                VALUES (%s, %s, 'correct', %s, %s)
                ON CONFLICT (trace_id) DO UPDATE SET
                  skill_name = EXCLUDED.skill_name,
                  policy_decision = EXCLUDED.policy_decision,
                  approved_for_training = EXCLUDED.approved_for_training,
                  reviewed_at = NOW()
                """,
                (row["trace_id"], row["skill_name"], row["policy_decision"], row["approved"]),
            )
        connection.commit()


def create_model_service(profile: str, catalog: str, schema: str) -> None:
    full_name = f"{catalog}.{schema}.governed_router"
    result = cli(
        profile,
        "ai-gateway",
        "get-model-service",
        f"model-services/{full_name}",
        check=False,
    )
    if result.returncode == 0:
        return
    config = {
        "comment": "Governed support router with PII blocking, attribution, split traffic, and fallback.",
        "config": {
            "routing": {
                "destinations": [
                    {
                        "name": "fast",
                        "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
                        "pay_per_token_config": {"model": "models/system.ai.databricks-gpt-5-nano"},
                        "traffic_percentage": 80,
                    },
                    {
                        "name": "quality",
                        "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
                        "pay_per_token_config": {
                            "model": "models/system.ai.databricks-gemini-3-1-flash-lite"
                        },
                        "traffic_percentage": 20,
                    },
                ],
                "fallback": {
                    "destinations": [
                        {
                            "name": "fallback",
                            "destination_type": "DESTINATION_TYPE_PAY_PER_TOKEN_FOUNDATION_MODEL",
                            "pay_per_token_config": {
                                "model": "models/system.ai.llama_v3_3_70b_instruct"
                            },
                            "traffic_percentage": 0,
                        }
                    ]
                },
            },
            "rate_limits": [
                {
                    "key": "RATE_LIMIT_KEY_USER_DEFAULT",
                    "renewal_period": "RATE_LIMIT_RENEWAL_PERIOD_MINUTE",
                    "requests": 60,
                },
                {
                    "key": "RATE_LIMIT_KEY_SERVICE",
                    "renewal_period": "RATE_LIMIT_RENEWAL_PERIOD_MINUTE",
                    "requests": 600,
                },
            ],
            "inference_table": {
                "parent": f"schemas/{catalog}.{schema}",
                "table_name_prefix": "governed_router",
            },
        },
    }
    cli(
        profile,
        "ai-gateway",
        "create-model-service",
        f"schemas/{catalog}.{schema}",
        "governed_router",
        "--json",
        json.dumps(config),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="fe-vm-lakebase-praneeth")
    parser.add_argument("--catalog", default="serverless_lakebase_praneeth_catalog")
    parser.add_argument("--schema", default="trace_to_tune")
    parser.add_argument("--lakebase-project", default="trace-to-tune")
    args = parser.parse_args()

    client = WorkspaceClient(profile=args.profile)
    warehouse = next(
        warehouse for warehouse in client.warehouses.list() if warehouse.enable_serverless_compute
    )
    seed_unity_catalog(client, warehouse.id, args.catalog, args.schema)
    seed_lakebase(args.profile, args.lakebase_project)
    create_model_service(args.profile, args.catalog, args.schema)
    Path("outputs/runtime").mkdir(parents=True, exist_ok=True)
    Path("outputs/runtime/bootstrap.json").write_text(
        json.dumps(
            {
                "profile": args.profile,
                "catalog": args.catalog,
                "schema": args.schema,
                "warehouse_id": warehouse.id,
                "lakebase_project": args.lakebase_project,
                "model_service": f"{args.catalog}.{args.schema}.governed_router",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
