# September 2026 research brief

Unity Gateway is the current Databricks governance plane for model services, model-provider services, MCP services, tools, and first-class skills. The core became generally available in August 2026. Service policies, Sensitive Data Detection, Skills, Smart Routing, agent registration, and unified tracing retain separate Beta labels.

The demo should center on the deterministic `system.ai.detect_sensitive_data` service policy. It can block or redact 15 structured categories, including email, phone, credit card, US SSN, Indian PAN, and Aadhaar. It runs on model services and model-provider services, not custom model serving endpoints or MCP services. A block returns HTTP 200 plus a structured `databricks_service_policy` decision, so the test must inspect the response body rather than expect an HTTP error.

Skills are `catalog.schema.skill` Unity Catalog securables. Unity Catalog records create, read, update, delete, and permission changes. Execution effectiveness still needs explicit MLflow spans or request tags.

The referenced `training-agents` repository is an Apache-2.0 operating context rather than a training package. This demo adapts its measurable SFT rung: synthetic reviewed traces, completion-only training, a frozen evaluation split, LoRA, smoke tests, and evidence before promotion. It does not copy or redistribute the upstream trace dataset.

AI Runtime exposes a Public Preview Jobs task for A10 and H100 serverless GPU workloads. Custom LLM Serving is Beta, uses a vLLM entrypoint, MLflow 3.12 or later, `env_pack="databricks_model_serving"`, and an `llm/v1/chat` contract.
