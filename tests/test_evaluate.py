import pytest

from trace_to_tune.evaluate import parse_skill, require_minimum_accuracy, routing_accuracy


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


def test_minimum_accuracy_is_enforced() -> None:
    require_minimum_accuracy(1.0, 1.0)
    with pytest.raises(RuntimeError):
        require_minimum_accuracy(0.75, 1.0)
    with pytest.raises(ValueError):
        require_minimum_accuracy(1.0, 1.1)
