---
id: B002-control
claim: C014
cell: ["C014", "lost-doorbell-control", "real-haiku", "claude", 1]
trials: 10
expect_rate: 1.0
control: B002-control
wait_timeout: 10
grade: tokens
---

Run B002 with B delivered through `agentctl send` rather than direct inbox creation. This is the non-fault baseline.
