from trace_to_tune.dataset import contains_raw_pii
from trace_to_tune.gateway_contract import PROBES, validation_errors


def test_pii_demo_payload_is_synthetic_but_detectable() -> None:
    payload = "Contact test.user@example.com and use synthetic PAN AFZPK7190K."
    assert contains_raw_pii(payload)


def test_pan_detection_uses_the_structural_holder_type_position() -> None:
    assert contains_raw_pii("Synthetic PAN AFZPK7190K")
    assert not contains_raw_pii("Invalid PAN-like value ABCDE1234F")


def test_policy_block_contract_is_not_an_http_error_contract() -> None:
    simulated_response = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "Blocked by policy"},
                "finish_reason": "content_filter",
            }
        ],
        "databricks_service_policy": {
            "action": "deny",
            "phase": "pre_call",
            "reason": "Detected sensitive data (EMAIL_ADDRESS).",
        },
    }
    assert simulated_response["databricks_service_policy"]["action"] == "deny"
    assert simulated_response["choices"][0]["finish_reason"] == "content_filter"


def test_gateway_probes_track_the_correct_skill_and_test_each_pii_class() -> None:
    probes = {probe.name: probe for probe in PROBES}
    assert probes["normal"].request_tags["skill"] == "order-status"
    assert probes["email"].request_tags["skill"] == "pii-safe-response"
    assert probes["pan"].request_tags["skill"] == "pii-safe-response"
    assert "@" in probes["email"].prompt
    assert contains_raw_pii(probes["pan"].prompt)


def test_gateway_validation_enforces_normal_and_pre_call_zero_token_blocks() -> None:
    block = {
        "status_code": 200,
        "body": {
            "choices": [{"finish_reason": "content_filter"}],
            "databricks_service_policy": {"action": "deny", "phase": "pre_call"},
            "usage": {"total_tokens": 0},
        },
    }
    output = {
        "normal": {"status_code": 200, "body": {"usage": {"total_tokens": 4}}},
        "email": block,
        "pan": block,
    }
    assert validation_errors(output, require_policy_block=True) == []

    output["pan"] = {**block, "body": {**block["body"], "usage": {"total_tokens": 1}}}
    assert "pan policy block consumed model tokens" in validation_errors(
        output, require_policy_block=True
    )
