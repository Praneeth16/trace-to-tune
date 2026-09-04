from __future__ import annotations

from trace_to_tune.dataset import ROUTABLE_SKILLS, SKILL_VERSION, contains_raw_pii


def request_tags(
    skill: str, *, workflow: str | None = "router-to-governed-response", test: str | None = None
) -> dict[str, str]:
    if skill not in ROUTABLE_SKILLS:
        raise ValueError(f"Unknown governed skill: {skill}")
    tags = {
        "project": "trace-to-tune",
        "skill": skill,
        "skill_version": SKILL_VERSION,
    }
    if workflow:
        tags["workflow"] = workflow
    if test:
        tags["test"] = test
    return tags


def policy_decision(response: dict[str, object]) -> str:
    policy = response.get("databricks_service_policy")
    if not isinstance(policy, dict):
        return "ALLOW"
    action = policy.get("action")
    return str(action).upper() if action else "UNKNOWN"


def require_safe_router_input(prompt: str) -> None:
    if contains_raw_pii(prompt):
        raise ValueError("Raw PII is not allowed to reach the custom router")
