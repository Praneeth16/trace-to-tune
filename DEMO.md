# Trace to Tune

## Audience and outcome

This demo is for AI platform and governance teams. It shows how a reviewed agent trace becomes a governed training example, a fine-tuned skill router, and a deployed custom LLM while Unity Gateway controls the traffic it supports today.

The closing proof is a side-by-side result: base versus tuned skill-routing accuracy, a normal governed request, independent deterministic Email and PAN blocks, five published governed skills, an MLflow agent trace, and a live custom LLM endpoint.

## Demo narrative

1. Route a normal request through `serverless_lakebase_praneeth_catalog.trace_to_tune.governed_router` and attach request tags for project and skill attribution.
2. Send synthetic email and Indian PAN data. The Beta Sensitive Data Detection service policy blocks the request before the model sees it.
3. Show the five governed skills in Unity Catalog and their audit activity.
4. Show reviewed trace outcomes in Lakebase and curated PII-safe training rows in Delta.
5. Run the Public Preview AI Runtime A10 job to fine-tune the skill router with LoRA.
6. Compare prompt-family-disjoint accuracy, register version 6 in Unity Catalog, and deploy it through Beta Custom LLM Serving.
7. Run the 24-example evaluation set through the deployed endpoint and show the verified 21/24 result plus the reimbursement-language failure family.
8. Run the MLflow-traced router-to-governed-response workflow and show skill/version attribution.
9. Close in the Unity Gateway usage dashboard and `system.ai_gateway.usage`, then show the custom endpoint result and telemetry.

## Unity Gateway component inventory

| Component | What to show in this workspace |
| --- | --- |
| Model services | `governed_router`, destination split, fallback, limits, policy, tags, inference table |
| Model provider services | No live provider service is configured; describe the surface without inventing evidence |
| MCP services | Built-in GitHub, Slack, Gmail, Drive, Calendar, DBSQL, sandbox, web search, Microsoft 365, and Atlassian services |
| Agent services | Beta registration and discovery only; do not imply runtime invocation |
| Skills | `order-status`, `refund-review`, `account-recovery`, `pii-safe-response`, and `trace-curation` with Unity Catalog permissions and audit activity |
| Governance and telemetry | UC access control, policy decision, usage, inference logs, MLflow run, and serving logs |

Sensitive Data Detection does not attach to MCP services. A later MCP extension would need a custom SQL service policy for tool arguments plus explicit tool filtering.

## Architecture boundary

The new Unity Gateway Model Service owns centralized PII blocking, routing, fallback, rate limits, inference logging, and request attribution. Governed skills are Unity Catalog assets whose control-plane operations are audited. Lakebase stores versioned operational review state; bootstrap-owned rows are marked explicitly, and content-addressed current approvals are promoted into Delta for training and evaluation. AI Runtime performs the fine-tune. Custom LLM Serving deploys the tuned model. Because custom endpoints do not inherit the Gateway policy, the combined workflow rejects raw Email/PAN before custom routing. An MLflow trace then connects routing, live governed-skill loading, and the governed response call.

Databricks does not support the new service policy on an MLflow custom model endpoint. The demo therefore keeps the governed model-service path and custom-model deployment path separate and says so on screen.

## Maturity labels as of September 4, 2026

| Capability | Status used in demo |
| --- | --- |
| Unity Gateway core | GA |
| Model services, routing, fallback, rate limits, usage | GA core surface |
| Service policies and Sensitive Data Detection | Beta |
| Unity Gateway Skills | Beta |
| Smart Routing and unified trace table | Beta, optional |
| AI Runtime Jobs task | Public Preview |
| Custom LLM Serving | Beta |
| Legacy custom-endpoint Unity Gateway controls | Limited; no PII guardrail |

## Safety

Only synthetic order identifiers and synthetic PII are used. Raw traces, model checkpoints, credentials, tokens, and generated model artifacts stay outside Git.
