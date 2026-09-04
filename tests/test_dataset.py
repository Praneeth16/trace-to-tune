import re

from trace_to_tune.dataset import (
    ROUTABLE_SKILLS,
    contains_raw_pii,
    generate_trace_rows,
    to_messages,
)


def test_dataset_is_balanced_and_split() -> None:
    rows = generate_trace_rows()
    assert len(rows) == 96
    assert sum(row["split"] == "train" for row in rows) == 72
    assert sum(row["split"] == "eval" for row in rows) == 24
    assert set(ROUTABLE_SKILLS) == {row["skill_name"] for row in rows} == {
        "order-status",
        "refund-review",
        "account-recovery",
        "pii-safe-response",
    }


def test_training_rows_contain_no_raw_pii() -> None:
    for row in generate_trace_rows():
        assert not contains_raw_pii(str(row["prompt"]))
        assert not contains_raw_pii(str(row["completion"]))


def test_evaluation_has_no_training_overlap() -> None:
    rows = generate_trace_rows()
    train = [row for row in rows if row["split"] == "train"]
    evaluation = [row for row in rows if row["split"] == "eval"]

    assert {row["prompt"] for row in train}.isdisjoint(row["prompt"] for row in evaluation)
    assert {row["source_family"] for row in train}.isdisjoint(
        row["source_family"] for row in evaluation
    )
    assert len({row["prompt"] for row in rows}) == len(rows)


def test_trace_ids_are_stable_and_content_derived() -> None:
    first = generate_trace_rows()
    second = generate_trace_rows()
    first_by_prompt = {row["prompt"]: row["trace_id"] for row in first}
    second_by_prompt = {row["prompt"]: row["trace_id"] for row in second}

    assert first_by_prompt == second_by_prompt
    assert len(set(first_by_prompt.values())) == len(first_by_prompt)
    assert all(re.fullmatch(r"trace-[a-z-]+-[0-9a-f]{16}", trace_id) for trace_id in first_by_prompt.values())
    assert all(":train:" not in row["source_family"] for row in first)
    assert all(":eval:" not in row["source_family"] for row in first)


def test_chat_format_has_completion_last() -> None:
    messages = to_messages(generate_trace_rows()[0])
    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
