from trace_to_tune.dataset import contains_raw_pii, generate_trace_rows, to_messages


def test_dataset_is_balanced_and_split() -> None:
    rows = generate_trace_rows()
    assert len(rows) == 96
    assert sum(row["split"] == "train" for row in rows) == 72
    assert sum(row["split"] == "eval" for row in rows) == 24
    assert {row["skill_name"] for row in rows} == {
        "order-status",
        "refund-review",
        "account-recovery",
        "pii-safe-response",
    }


def test_training_rows_contain_no_raw_pii() -> None:
    for row in generate_trace_rows():
        assert not contains_raw_pii(str(row["prompt"]))
        assert not contains_raw_pii(str(row["completion"]))


def test_chat_format_has_completion_last() -> None:
    messages = to_messages(generate_trace_rows()[0])
    assert [message["role"] for message in messages] == ["system", "user", "assistant"]
