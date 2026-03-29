# Roadmap checker hook

`roadmap-checker.py` is a Claude Code **Stop hook** that drives autonomous sequential implementation. When Claude finishes a session, the hook checks for the next unblocked task in `.dev/task-*.md` and injects it as a continuation prompt — blocking Claude from stopping until the full roadmap is done.

## How it works

1. Scans `.dev/task-*.md` and parses YAML frontmatter from each file
2. Finds the highest-priority task where `status: ready` and all `depends_on` tasks are `done`
3. If found: outputs `{"decision": "block", "reason": "<prompt>"}` — Claude receives the task description and continues
4. If not found and no tasks remain: exits 0 — Claude stops normally
5. Writes state to `.claude/roadmap-hook-state.json` (block count, last task)

## Task file format

Task files live at `.dev/task-NNN.md` (e.g. `task-001.md`). Each file has YAML frontmatter followed by a detailed implementation spec.

```yaml
---
id: task-001
title: Short imperative title (e.g. "Add GoogleCalendarProvider")
status: ready          # ready | in-progress | done | needs-research | blocked
milestone: 1           # integer (0–5) or "deferred"
priority: p1           # p0 (critical) | p1 (high) | p2 (normal) | p3 (low)
estimated_effort: M    # S=hours, M=half-day, L=full-day, XL=multi-day
depends_on:
  - task-000           # IDs of tasks that must be done first
blocks: []             # IDs of tasks this one unblocks (informational)
parallel_with: []      # IDs of tasks that can run concurrently
---

## Goal

One paragraph: what this task delivers and why it matters.

## Context

Background the implementer needs. Link to relevant files, existing patterns to follow, known gotchas.

## Files

| File | Action | Description |
|---|---|---|
| `src/iobox/providers/google/calendar.py` | create | GoogleCalendarProvider implementation |
| `tests/unit/test_google_calendar_provider.py` | create | Unit tests |

## Implementation notes

Step-by-step or bullet list of what to do. Be specific enough that Claude can execute without additional context.

## Test strategy

What tests to write, what to mock, what edge cases to cover.

## Definition of done

- [ ] All files listed above exist and match the spec
- [ ] `make test` passes with no failures
- [ ] `make type-check` passes
- [ ] `make lint` passes
- [ ] `status` updated to `done`
```

## Writing good task files

**Scope one thing per task.** A task should be completable in one Claude session (S–L effort). If a feature requires research, data design, implementation, and tests — split it.

**Make the definition of done mechanical.** "It works" is not done. List specific files, specific test counts, specific `make` commands that must pass.

**Explicit dependencies.** If task B needs task A's types or interfaces, add `depends_on: [task-A]`. The hook will not schedule B until A is done.

**Front-load context.** The hook prompt tells Claude to read the task file and implement it completely. Put everything Claude needs — file paths, existing patterns to follow, invariants to preserve, gotchas — in the task file itself. Don't assume Claude remembers prior sessions.

**Use milestones for ordering, priority for urgency.** Milestone groups related work (all providers = milestone 1, all CLI commands = milestone 2). Priority breaks ties within a milestone: p0 = blocking/critical, p1 = high value, p2 = normal, p3 = nice-to-have.

**Research tasks.** If you don't know the answer yet, set `status: needs-research` and describe the question. The hook skips `needs-research` tasks (they can't be auto-implemented). Resolve the research question manually, then set the task to `ready`.

## Operating the loop

**Start the loop**: Just do some work and stop. If `task-*.md` files with `status: ready` exist, the hook fires automatically on the next stop.

**Pause after N sessions**:
```bash
export ROADMAP_MAX_BLOCKS=3   # stop after 3 autonomous continuations
```

**Check progress**:
```bash
grep "status:" .dev/task-*.md
cat .claude/roadmap-hook-state.json
```

**Reset state** (e.g. after resolving a blocked task):
```bash
rm .claude/roadmap-hook-state.json
```

**Disable the hook**: Remove or rename `roadmap-checker.py`, or remove it from `.claude/settings.json` hooks config.

## Milestone and priority reference

| Milestone | Meaning |
|---|---|
| `0` | Foundation / critical fixes — must ship first |
| `1`–`5` | Feature milestones in delivery order |
| `deferred` | Skipped until all active milestones are done |

| Priority | Meaning |
|---|---|
| `p0` | Blocking — loop prefers this above all others in the milestone |
| `p1` | High value — schedule early |
| `p2` | Normal — default |
| `p3` | Low — nice-to-have, scheduled last |

Within a milestone, tasks are sorted by priority then by file name (alphabetical). Dependencies override sort order.
