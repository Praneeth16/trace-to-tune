from __future__ import annotations

import json
import re

JSON_OBJECT = re.compile(r"\{.*?\}", re.DOTALL)


def parse_skill(text: str) -> str | None:
    match = JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    skill = value.get("skill")
    return skill if isinstance(skill, str) else None


def routing_accuracy(predictions: list[str], expected: list[str]) -> float:
    if not expected or len(predictions) != len(expected):
        raise ValueError("predictions and expected must be non-empty and equal length")
    correct = sum(
        parse_skill(prediction) == label for prediction, label in zip(predictions, expected)
    )
    return correct / len(expected)
