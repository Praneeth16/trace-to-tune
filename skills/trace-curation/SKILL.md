---
name: trace-curation
description: Review agent traces before they enter a supervised fine-tuning dataset. Use when promoting production or synthetic traces into training data.
---

# Trace curation

1. Keep only traces with a verified task outcome.
2. Remove hidden reasoning and raw personal or secret data.
3. Preserve visible user, assistant, tool-call, and tool-result turns.
4. Label the chosen skill, skill version, policy decision, and evaluation split.
5. Reject duplicates, leakage from the held-out set, and traces without a clear target completion.
