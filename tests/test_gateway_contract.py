from trace_to_tune.dataset import contains_raw_pii


def test_pii_demo_payload_is_synthetic_but_detectable() -> None:
    payload = "Contact test.user@example.com and use demo PAN ABCDE1234F."
    assert contains_raw_pii(payload)


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
