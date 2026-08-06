# Worker protocol

You are running in a terminal window. **A human can see this window and may type
to you directly.** An orchestrator can also address you, by leaving files in your
inbox. Both are real participants — treat a message from either as genuine.

## Check your inbox at the start of every turn

Your inbox path was given in your bootstrap message. Read any file you have not
already handled, lowest number first.

This matters: instructions are delivered by writing a file and then typing a
one-line pointer at your window. If that keystroke is ever lost or garbled, the
instruction is still sitting in your inbox — but only if you look.

## Report back with `reply`

```bash
agentctl reply --status reply      # answering, work done, findings delivered
agentctl reply --status question   # you need a human decision to continue
agentctl reply --status blocked    # something outside your control stops you
```

Body on stdin. The absolute path to `agentctl` was given in your bootstrap
message.

```bash
agentctl reply --status reply <<'EOF'
Reviewed the diff. Two issues, both in the error path: ...
EOF
```

**Your identity comes from the environment. Never pass `--run` or `--agent`
yourself** — they are set for you at startup and guessing them writes your reply
into another agent's mailbox.

`question` and `blocked` are how you hand control back. Use them when you are
genuinely stuck; do not use them to check in.

## Codex workers

Codex workers use this same inbox/outbox protocol, but do not emit the Claude
lifecycle hooks. Read the bootstrap and inbox files, then use `reply` for your
final result, question, or blocker. The orchestrator can observe those reports
and terminal liveness, but cannot infer Codex turn boundaries.

## Two rules

**Never assume the orchestrator can see your screen.** It cannot read your
reasoning, your output, or anything you print. Anything it must know goes
through `reply`. Work you did not report is work that did not happen.

**Do not manage other workers.** `spawn`, `close`, `reap` and `close-run` belong
to the orchestrator. Workers do not start or stop workers.
