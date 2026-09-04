from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass

SYSTEM_PROMPT = (
    "Choose exactly one governed skill for the support request. "
    "Return JSON only with keys skill and reason. Never repeat personal data."
)
SKILL_VERSION = "1.0.0"


@dataclass(frozen=True)
class SkillTemplate:
    skill: str
    train_requests: tuple[str, ...]
    eval_requests: tuple[str, ...]
    reasons: tuple[str, ...]


SKILL_TEMPLATES = (
    SkillTemplate(
        skill="order-status",
        train_requests=(
            "Where is order {case_id}?",
            "My delivery for {case_id} has not arrived.",
            "Check the shipping status of order {case_id}.",
            "Tell me the latest carrier scan for {case_id}.",
            "Has parcel {case_id} been handed to the carrier?",
            "Find the warehouse departure status for {case_id}.",
        ),
        eval_requests=(
            "Give me the current logistics checkpoint for parcel {case_id}.",
            "What delivery progress should I expect for shipment {case_id}?",
        ),
        reasons=(
            "The request asks for shipment state.",
            "Order lookup is the narrowest safe skill.",
        ),
    ),
    SkillTemplate(
        skill="refund-review",
        train_requests=(
            "Can I get a refund for order {case_id}?",
            "Review order {case_id} for a refund.",
            "The product in {case_id} was damaged. What are my refund options?",
            "Check whether {case_id} is still inside the return window.",
            "Evaluate whether the charge for {case_id} can be reversed.",
            "Is purchase {case_id} eligible for money back?",
        ),
        eval_requests=(
            "Assess whether purchase {case_id} is eligible for reimbursement.",
            "I want the payment on {case_id} returned; which review applies?",
        ),
        reasons=(
            "The user asks for a refund decision.",
            "Refund policy review is required.",
        ),
    ),
    SkillTemplate(
        skill="account-recovery",
        train_requests=(
            "I cannot sign in; start recovery case {case_id}.",
            "Help restore access after failed logins for case {case_id}.",
            "My account is locked. Open the safe recovery flow for {case_id}.",
            "Case {case_id}: my password reset link expired.",
            "I lost access to my authenticator for case {case_id}.",
            "Verify the next safe account-unlock step for {case_id}.",
        ),
        eval_requests=(
            "What secure process restores my login for case {case_id}?",
            "The verification step failed for {case_id}; how can I recover access?",
        ),
        reasons=(
            "The request concerns account access.",
            "Use the identity-safe recovery procedure.",
        ),
    ),
    SkillTemplate(
        skill="pii-safe-response",
        train_requests=(
            "Case {case_id}: rewrite this reply without exposing [EMAIL_ADDRESS].",
            "Remove [PHONE_NUMBER] before drafting response {case_id}.",
            "The trace for {case_id} contains [IN_PAN]. Produce a privacy-safe summary.",
            "Keep [AADHAAR_NUMBER] redacted in the answer for {case_id}.",
            "Sanitize [CREDIT_CARD_NUMBER] from support note {case_id}.",
            "Draft a minimal reply for {case_id} while preserving [PERSON_NAME].",
        ),
        eval_requests=(
            "Redact [PHONE_NUMBER] while summarizing support item {case_id}.",
            "Do not expose [AADHAAR_NUMBER] in the reply for {case_id}.",
        ),
        reasons=(
            "The request contains a redaction marker.",
            "Privacy-safe handling must run first.",
        ),
    ),
)

ROUTABLE_SKILLS = tuple(template.skill for template in SKILL_TEMPLATES)

RAW_PII_PATTERNS = (
    re.compile(r"\b[A-Z]{3}[PCHABGJLFT][A-Z]\d{4}[A-Z]\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
)


def generate_trace_rows(
    train_per_skill: int = 18, eval_per_skill: int = 6
) -> list[dict[str, object]]:
    if train_per_skill < 1 or eval_per_skill < 1:
        raise ValueError("train_per_skill and eval_per_skill must both be positive")

    rng = random.Random(42)
    rows: list[dict[str, object]] = []
    for template in SKILL_TEMPLATES:
        for split, count, requests in (
            ("train", train_per_skill, template.train_requests),
            ("eval", eval_per_skill, template.eval_requests),
        ):
            for index in range(count):
                family_index = index % len(requests)
                case_id = f"DEMO-{1000 + rng.randrange(9000)}"
                request = requests[family_index].format(case_id=case_id)
                completion = json.dumps(
                    {
                        "skill": template.skill,
                        "reason": template.reasons[index % len(template.reasons)],
                    },
                    separators=(",", ":"),
                )
                family_digest = hashlib.sha256(requests[family_index].encode()).hexdigest()[:12]
                trace_digest = hashlib.sha256(
                    f"{template.skill}|{SKILL_VERSION}|{request}|{completion}".encode()
                ).hexdigest()[:16]
                rows.append(
                    {
                        "trace_id": f"trace-{template.skill}-{trace_digest}",
                        "prompt": request,
                        "completion": completion,
                        "skill_name": template.skill,
                        "skill_version": SKILL_VERSION,
                        "source_family": f"{template.skill}:{family_digest}",
                        "split": split,
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
