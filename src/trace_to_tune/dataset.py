from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

SYSTEM_PROMPT = (
    "Choose exactly one governed skill for the support request. "
    "Return JSON only with keys skill and reason. Never repeat personal data."
)


@dataclass(frozen=True)
class SkillTemplate:
    skill: str
    requests: tuple[str, ...]
    reasons: tuple[str, ...]


SKILL_TEMPLATES = (
    SkillTemplate(
        "order-status",
        (
            "Where is order {order_id}?",
            "My delivery for {order_id} has not arrived.",
            "Check the shipping status of order {order_id}.",
        ),
        ("The request asks for shipment state.", "Order lookup is the narrowest safe skill."),
    ),
    SkillTemplate(
        "refund-review",
        (
            "Can I get a refund for order {order_id}?",
            "Review order {order_id} for a refund.",
            "The product in {order_id} was damaged. What are my refund options?",
        ),
        ("The user asks for a refund decision.", "Refund policy review is required."),
    ),
    SkillTemplate(
        "account-recovery",
        (
            "I cannot sign in to my account.",
            "Help me recover access after too many failed logins.",
            "My account is locked. Start the safe recovery flow.",
        ),
        ("The request concerns account access.", "Use the identity-safe recovery procedure."),
    ),
    SkillTemplate(
        "pii-safe-response",
        (
            "Rewrite this reply without exposing [EMAIL_ADDRESS].",
            "Remove [PHONE_NUMBER] before drafting the response.",
            "The trace contains [IN_PAN]. Produce a privacy-safe summary.",
        ),
        ("The request contains a redaction marker.", "Privacy-safe handling must run first."),
    ),
)


RAW_PII_PATTERNS = (
    re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
)


def generate_trace_rows(
    train_per_skill: int = 18, eval_per_skill: int = 6
) -> list[dict[str, object]]:
    rng = random.Random(42)
    rows: list[dict[str, object]] = []
    for template in SKILL_TEMPLATES:
        total = train_per_skill + eval_per_skill
        for index in range(total):
            request = template.requests[index % len(template.requests)].format(
                order_id=f"DEMO-{1000 + rng.randrange(9000)}"
            )
            completion = json.dumps(
                {
                    "skill": template.skill,
                    "reason": template.reasons[index % len(template.reasons)],
                },
                separators=(",", ":"),
            )
            rows.append(
                {
                    "trace_id": f"trace-{template.skill}-{index:03d}",
                    "prompt": request,
                    "completion": completion,
                    "skill_name": template.skill,
                    "skill_version": "1.0.0",
                    "split": "train" if index < train_per_skill else "eval",
                    "approved": True,
                    "policy_decision": "ALLOW",
                }
            )
    rng.shuffle(rows)
    return rows


def contains_raw_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in RAW_PII_PATTERNS)


def to_messages(row: dict[str, object]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": str(row["prompt"])},
        {"role": "assistant", "content": str(row["completion"])},
    ]
