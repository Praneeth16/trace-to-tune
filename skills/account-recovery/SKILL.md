---
name: account-recovery
description: Guide a user through identity-safe account recovery. Use for locked accounts, failed sign-in, and expired reset flows.
---

# Account recovery

1. Never ask for a password, recovery code, government identifier, or payment data.
2. Use the approved identity-verification flow before changing account access.
3. Give the smallest safe next step and state when human review is required.
4. Route unexpected personal data through the Unity Gateway sensitive-data policy.
5. Record `skill_name=account-recovery`, the skill version, and the policy decision in the trace.
