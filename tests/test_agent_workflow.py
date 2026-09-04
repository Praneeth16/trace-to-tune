import pytest

from trace_to_tune.workflow import policy_decision, request_tags, require_safe_router_input


def test_agent_workflow_tags_selected_governed_skill() -> None:
    tags = request_tags("order-status")
    assert tags == {
        "project": "trace-to-tune",
        "workflow": "router-to-governed-response",
        "skill": "order-status",
        "skill_version": "1.0.0",
    }


def test_agent_workflow_rejects_unknown_skill() -> None:
    with pytest.raises(ValueError):
        request_tags("not-governed")


def test_policy_decision_distinguishes_allow_and_deny() -> None:
    assert policy_decision({"choices": []}) == "ALLOW"
    assert policy_decision({"databricks_service_policy": {"action": "deny"}}) == "DENY"


def test_raw_pii_is_rejected_before_custom_routing() -> None:
    require_safe_router_input("Where is order DEMO-2048?")
    with pytest.raises(ValueError, match="not allowed to reach the custom router"):
        require_safe_router_input("Contact test.user@example.com")
    with pytest.raises(ValueError, match="not allowed to reach the custom router"):
        require_safe_router_input("Use PAN AFZPK7190K")
