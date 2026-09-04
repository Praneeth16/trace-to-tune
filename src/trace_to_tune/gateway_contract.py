from __future__ import annotations

from dataclasses import dataclass

from trace_to_tune.workflow import request_tags


@dataclass(frozen=True)
class Probe:
    name: str
    prompt: str
    skill: str
    expects_block: bool

    @property
    def request_tags(self) -> dict[str, str]:
        return request_tags(self.skill, workflow=None, test=self.name)


PROBES = (
    Probe(
        name="normal",
        prompt="Choose the safest skill for checking order DEMO-2048.",
        skill="order-status",
        expects_block=False,
    ),
    Probe(
        name="email",
        prompt="Contact test.user@example.com about support case DEMO-3101.",
        skill="pii-safe-response",
        expects_block=True,
    ),
    Probe(
        name="pan",
        prompt="Use synthetic Indian PAN AFZPK7190K for support case DEMO-3102.",
        skill="pii-safe-response",
        expects_block=True,
    ),
)


def validation_errors(output: dict[str, object], require_policy_block: bool) -> list[str]:
    errors: list[str] = []
    normal = output.get("normal", {})
    normal_body = normal.get("body", {}) if isinstance(normal, dict) else {}
    normal_usage = normal_body.get("usage", {}) if isinstance(normal_body, dict) else {}
    if not isinstance(normal, dict) or normal.get("status_code") != 200:
        errors.append("normal request did not return HTTP 200")
    if isinstance(normal_body, dict) and normal_body.get("databricks_service_policy"):
        errors.append("normal request was unexpectedly blocked by policy")
    if not isinstance(normal_usage, dict) or normal_usage.get("total_tokens", 0) <= 0:
        errors.append("normal request did not record model tokens")

    if not require_policy_block:
        return errors

    for probe in (item for item in PROBES if item.expects_block):
        result = output.get(probe.name, {})
        body = result.get("body", {}) if isinstance(result, dict) else {}
        policy = body.get("databricks_service_policy", {}) if isinstance(body, dict) else {}
        choices = body.get("choices", [{}]) if isinstance(body, dict) else [{}]
        finish_reason = choices[0].get("finish_reason") if choices else None
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        if not isinstance(result, dict) or result.get("status_code") != 200:
            errors.append(f"{probe.name} policy response did not return HTTP 200")
        if not isinstance(policy, dict) or policy.get("action") != "deny":
            errors.append(f"{probe.name} policy action was not deny")
        if not isinstance(policy, dict) or policy.get("phase") != "pre_call":
            errors.append(f"{probe.name} policy phase was not pre_call")
        if finish_reason != "content_filter":
            errors.append(f"{probe.name} finish_reason was not content_filter")
        if not isinstance(usage, dict) or usage.get("total_tokens") != 0:
            errors.append(f"{probe.name} policy block consumed model tokens")
    return errors
