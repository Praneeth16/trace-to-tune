---
name: pii-safe-response
description: Remove or replace sensitive-data markers before drafting a support response. Use when a trace or request contains PII or a redaction placeholder.
---

# PII-safe response

1. Stop if raw personal data is present and route the request through the Unity Gateway sensitive-data policy.
2. Keep bracketed redaction markers in place. Never reconstruct the original value.
3. Draft the minimum response needed to resolve the request.
4. Record `skill_name=pii-safe-response`, the skill version, and the policy decision in the trace.
