# TICKET-010: worktree isolation defeated by orchestrator-path leak in bootstrap message

## Overview
`agentctl spawn --worktree` is supposed to give a worker its own isolated git checkout so
parallel agents can't step on each other's files. In practice, observed live during the
CVviewer portfolio-cleanup run (2026-08-10), a `--worktree` worker (`ci-implementer`) never
touched its own worktree at all — it read `pyproject.toml`, wrote `.github/workflows/ci.yml`,
and ran every Bash command against the *source* repo's absolute path
(`/Users/.../My Drive/Projects/CVviewer/...`) instead of its assigned worktree
(`~/.local/state/agent-tabs/<repo>/<run>/worktrees/ci-implementer/`). The worktree itself
ended up completely empty; `git log` there never advanced past the source repo's existing HEAD.
This happened to be harmless in that run (no other agent touched the same files), but it means
`--worktree` is not actually providing the isolation it promises — the next parallel run with
real file overlap could silently corrupt or race against the live repo instead of staying
contained.

## Root cause
`bootstrap_body_for()` (`agentctl.py` ~line 1263) builds the worker's inbox bootstrap message
using:
```python
protocol = Path(__file__).resolve().parent / "WORKER.md"
...
f"Read and follow `{protocol}` for inbox checking and `agentctl reply` reporting.\n\n"
...
f"- Report with `{Path(__file__).resolve()} reply --status reply|question|blocked` ..."
```
`Path(__file__)` resolves to wherever the **orchestrator's own** `agentctl.py` process is
running from — the source repo — not the worker's worktree copy of the identically-named file
(which does exist, since `add_worktree()` checks out `HEAD` in full, `.agent/skills/` included).
The worker's very first message therefore anchors it to the orchestrator's absolute path for
its core protocol file and its own reply mechanism. Confirmed via the worker's session
transcript (`~/.claude/projects/<worktree-path-hash>/*.jsonl`): every subsequent Read/Write/Bash
call used the source-repo absolute path, matching the one path it was handed at bootstrap,
rather than switching to its actual shell cwd (which `backend.open()` does correctly set to the
worktree — the cwd itself was never wrong, only the model's frame of reference was).

## Implementation Steps
1. **`agentctl.py` — `bootstrap_body_for` (~line 1263)**: accept the worker's own `working_dir`
   (already computed in `spawn()` as `worktree_path or source`, ~line 1478) as a parameter, and
   derive `protocol` and the reply-command path from *that* directory instead of
   `Path(__file__).resolve()`. Since `add_worktree()` guarantees a full checkout, the worktree's
   own `.agent/skills/agent-tabs/agentctl.py` and `WORKER.md` are always present at the same
   relative location — resolve against `working_dir`, not the orchestrator's `__file__`.
2. **`spawn()` (~line 1478)**: thread `working_dir` through to the `write_inbox` /
   `bootstrap_body_for` call (currently at the line building `bootstrap_path`), which today only
   receives `paths`, `name`, `role_path`, `task` — add `working_dir` (or derive the relevant
   paths beforehand and pass strings) so the fix in step 1 has what it needs.
3. **Verify no other bootstrap-message path derivation has the same `__file__`-vs-`working_dir`
   confusion** — grep `agentctl.py` for other uses of `Path(__file__)` inside functions called
   during `spawn()`, not just `bootstrap_body_for`.
4. **Add a regression test**: spawn a worker with `--worktree` against a throwaway repo fixture,
   read its generated inbox bootstrap message, and assert the `WORKER.md` and reply-command paths
   are under the worker's worktree directory, not the source repo's.

## Explicit Constraints & Warnings
- Do not assume the worker's shell cwd was ever wrong — it wasn't (`backend.open()` correctly
  passes `working_dir`). This is purely a content-of-the-bootstrap-message bug; don't go looking
  for a cwd/env bug that isn't there.
- Do not change `add_worktree()`'s checkout behavior — it already does the right thing
  (`git worktree add --detach <target> HEAD`, full checkout). The fix is scoped to what the
  bootstrap message *tells the worker*, not to what files exist where.
- This is a prompting/framing bug, not a hard technical isolation failure — a worker could in
  principle still choose to hardcode the source path even after this fix. The fix removes the
  bug's most likely cause (an authoritative-looking absolute path handed to it at bootstrap,
  which it then generalized from), it doesn't add an enforcement mechanism. If stronger isolation
  is wanted later, that's a separate ticket (e.g. actually restricting worker file-tool access to
  its worktree path).

## Acceptance Criteria
- [Automated] New regression test: spawning with `--worktree` produces a bootstrap message whose
  `WORKER.md` and reply-command paths are both under the assigned worktree directory.
- [Manual] Re-run a `--worktree` spawn on a real task that reads/writes files, and confirm via
  its session transcript (or simply `git status`/`git log` in the worktree afterward) that it
  operated entirely within its own worktree, not the source repo.
