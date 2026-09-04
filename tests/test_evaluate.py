import pytest

from trace_to_tune.evaluate import parse_skill, routing_accuracy


def test_parse_skill_ignores_surrounding_text() -> None:
    assert parse_skill('Result: {"skill":"refund-review","reason":"refund"}') == "refund-review"


def test_parse_skill_rejects_invalid_output() -> None:
    assert parse_skill("refund-review") is None


def test_routing_accuracy() -> None:
    predictions = ['{"skill":"order-status"}', '{"skill":"refund-review"}']
    assert routing_accuracy(predictions, ["order-status", "account-recovery"]) == 0.5


def test_routing_accuracy_validates_lengths() -> None:
    with pytest.raises(ValueError):
        routing_accuracy([], [])
