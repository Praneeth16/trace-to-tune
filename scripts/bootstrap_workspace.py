from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient
from psycopg.rows import dict_row

from trace_to_tune.dataset import ROUTABLE_SKILLS, generate_trace_rows


def cli(profile: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["databricks", *args, "--profile", profile, "-o", "json"],
            check=check,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise RuntimeError(f"Databricks CLI command failed: {detail}") from error


def execute_sql(client: WorkspaceClient, warehouse_id: str, statement: str) -> None:
    response = client.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=statement,
        wait_timeout="50s",
    )
    if response.status and response.status.error:
        raise RuntimeError(response.status.error.message)


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_namespace(catalog: str, schema: str) -> str:
    if not IDENTIFIER.fullmatch(catalog) or not IDENTIFIER.fullmatch(schema):
        raise ValueError("catalog and schema must be unquoted SQL identifiers")
    return f"{catalog}.{schema}"


def sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        value = value.isoformat()
    return "'" + str(value).replace("'", "''") + "'"


def prepare_unity_catalog(
    client: WorkspaceClient, warehouse_id: str, catalog: str, schema: str
) -> None:
    namespace = validate_namespace(catalog, schema)
    execute_sql(client, warehouse_id, f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
    execute_sql(
        client,
        warehouse_id,
        f"CREATE VOLUME IF NOT EXISTS {namespace}.artifacts "
        "COMMENT 'Trace-to-tune model artifacts and run evidence'",
    )


def materialize_curated_traces(
    client: WorkspaceClient,
    warehouse_id: str,
    catalog: str,
    schema: str,
    reviewed_rows: list[dict[str, object]],
) -> None:
    if not reviewed_rows:
        raise RuntimeError("Lakebase has no approved, policy-allowed traces to promote")

    namespace = validate_namespace(catalog, schema)
    columns = (
        "trace_id",
        "prompt",
        "completion",
        "skill_name",
        "skill_version",
        "source_family",
        "split",
        "approved",
        "policy_decision",
        "reviewer_outcome",
        "reviewed_at",
    )
    values = ",\n".join(
        "(" + ",".join(sql_literal(row[column]) for column in columns) + ")"
        for row in reviewed_rows
    )
    execute_sql(
        client,
        warehouse_id,
        f"""
        CREATE OR REPLACE TABLE {namespace}.curated_traces
        USING DELTA
        COMMENT 'Lakebase-approved synthetic traces for trace-to-tune training'
        AS SELECT
          trace_id, prompt, completion, skill_name, skill_version, source_family, split,
          approved, policy_decision, reviewer_outcome,
          CAST(reviewed_at AS TIMESTAMP) AS curated_at
        FROM VALUES
          {values}
        AS reviewed(
          trace_id, prompt, completion, skill_name, skill_version, source_family, split,
          approved, policy_decision, reviewer_outcome, reviewed_at
        )
        """,
    )


def seed_lakebase(profile: str, project: str) -> list[dict[str, object]]:
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

    endpoints: list[dict[str, object]] = []
    endpoint: dict[str, object] | None = None
    for _ in range(30):
        payload = cli(
            profile,
            "postgres",
            "list-endpoints",
            f"projects/{project}/branches/production",
        ).stdout
        endpoints = json.loads(payload)
        endpoint = next(
            (
                item
                for item in endpoints
                if item.get("status", {}).get("current_state") in {"ACTIVE", "IDLE"}
                and str(item.get("name", "")).endswith("/primary")
            ),
            None,
        ) or next(
            (
                item
                for item in endpoints
                if item.get("status", {}).get("current_state") in {"ACTIVE", "IDLE"}
            ),
            None,
        )
        if endpoint:
            break
        time.sleep(5)
    if not endpoint:
        states = [item.get("status", {}).get("current_state") for item in endpoints]
        raise RuntimeError(f"Lakebase endpoint did not become ready; states={states}")
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
    with psycopg.connect(app_dsn, row_factory=dict_row) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trace_feedback (
              trace_id TEXT PRIMARY KEY,
              prompt TEXT NOT NULL,
              completion TEXT NOT NULL,
              skill_name TEXT NOT NULL,
              skill_version TEXT NOT NULL,
              source_family TEXT NOT NULL,
              record_source TEXT NOT NULL DEFAULT 'external',
              split TEXT NOT NULL CHECK (split IN ('train', 'eval')),
              reviewer_outcome TEXT NOT NULL,
              policy_decision TEXT NOT NULL,
              approved_for_training BOOLEAN NOT NULL,
              reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        for column, data_type in (
            ("prompt", "TEXT"),
            ("completion", "TEXT"),
            ("skill_version", "TEXT"),
            ("source_family", "TEXT"),
            ("record_source", "TEXT"),
            ("split", "TEXT"),
        ):
            connection.execute(
                f"ALTER TABLE trace_feedback ADD COLUMN IF NOT EXISTS {column} {data_type}"
            )
        generated_rows = generate_trace_rows()
        current_trace_ids = [str(row["trace_id"]) for row in generated_rows]
        legacy_trace_ids = [
            f"trace-{skill}-{index:03d}"
            for skill in ROUTABLE_SKILLS
            for index in range(24)
        ]
        connection.execute(
            """
            UPDATE trace_feedback
            SET record_source = 'synthetic-bootstrap'
            WHERE record_source IS NULL
              AND trace_id = ANY(%s)
            """,
            (current_trace_ids + legacy_trace_ids,),
        )
        connection.execute(
            """
            UPDATE trace_feedback
            SET approved_for_training = FALSE
            WHERE record_source = 'synthetic-bootstrap'
              AND NOT (trace_id = ANY(%s))
            """,
            (current_trace_ids,),
        )
        for row in generated_rows:
            connection.execute(
                """
                INSERT INTO trace_feedback
                  (trace_id, prompt, completion, skill_name, skill_version, source_family,
                   record_source, split, reviewer_outcome, policy_decision, approved_for_training)
                VALUES (%s, %s, %s, %s, %s, %s, 'synthetic-bootstrap', %s, 'correct', %s, %s)
                ON CONFLICT (trace_id) DO UPDATE SET
                  prompt = EXCLUDED.prompt,
                  completion = EXCLUDED.completion,
                  skill_name = EXCLUDED.skill_name,
                  skill_version = EXCLUDED.skill_version,
                  source_family = EXCLUDED.source_family,
                  record_source = EXCLUDED.record_source,
                  split = EXCLUDED.split
                """,
                (
                    row["trace_id"],
                    row["prompt"],
                    row["completion"],
                    row["skill_name"],
                    row["skill_version"],
                    row["source_family"],
                    row["split"],
                    row["policy_decision"],
                    row["approved"],
                ),
            )
        approved_rows = connection.execute(
            """
            SELECT trace_id, prompt, completion, skill_name, skill_version, source_family, split,
                   approved_for_training AS approved, policy_decision, reviewer_outcome,
                   reviewed_at
            FROM trace_feedback
            WHERE approved_for_training = TRUE
              AND reviewer_outcome = 'correct'
              AND policy_decision = 'ALLOW'
              AND prompt IS NOT NULL
              AND completion IS NOT NULL
              AND trace_id = ANY(%s)
            ORDER BY trace_id
            """,
            (current_trace_ids,),
        ).fetchall()
        connection.commit()
    return [dict(row) for row in approved_rows]


def model_service_config(catalog: str, schema: str) -> dict[str, object]:
    validate_namespace(catalog, schema)
    return {
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


def remove_read_only_service_fields(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: remove_read_only_service_fields(item)
            for key, item in value.items()
            if key not in {"is_deleted", "table"}
        }
    if isinstance(value, list):
        return [remove_read_only_service_fields(item) for item in value]
    return value


def ensure_model_service(profile: str, catalog: str, schema: str) -> None:
    full_name = f"{catalog}.{schema}.governed_router"
    resource_name = f"model-services/{full_name}"
    desired = model_service_config(catalog, schema)
    result = cli(
        profile,
        "ai-gateway",
        "get-model-service",
        resource_name,
        check=False,
    )
    if result.returncode == 0:
        current = json.loads(result.stdout)
        actual = remove_read_only_service_fields(
            {"comment": current.get("comment"), "config": current.get("config")}
        )
        if actual != desired:
            raise RuntimeError(
                "Unity Gateway model service configuration has drifted. "
                "Reconcile it deliberately in the UI and reattach the Beta policy; "
                "updating the service can detach policy enforcement."
            )
        return
    cli(
        profile,
        "ai-gateway",
        "create-model-service",
        f"schemas/{catalog}.{schema}",
        "governed_router",
        "--json",
        json.dumps(desired),
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
    prepare_unity_catalog(client, warehouse.id, args.catalog, args.schema)
    approved_rows = seed_lakebase(args.profile, args.lakebase_project)
    materialize_curated_traces(
        client, warehouse.id, args.catalog, args.schema, approved_rows
    )
    ensure_model_service(args.profile, args.catalog, args.schema)
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
                "promoted_rows": len(approved_rows),
                "rows_by_split": dict(Counter(str(row["split"]) for row in approved_rows)),
                "rows_by_skill": dict(
                    Counter(str(row["skill_name"]) for row in approved_rows)
                ),
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
