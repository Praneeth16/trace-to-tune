---
name: order-status
description: Retrieve shipment state and delivery milestones without changing an order. Use for tracking and arrival questions.
---

# Order status

1. Require an order reference that contains no personal data.
2. Read shipment status only; never alter fulfillment records.
3. Return the latest confirmed carrier milestone and timestamp.
4. If the order cannot be found, ask for a safe reference rather than personal data.
5. Record `skill_name=order-status`, the skill version, and the policy decision in the trace.
