#!/usr/bin/env python3
"""
Roadmap-checker stop hook for iobox.

Runs when Claude stops. Finds the next unblocked, ready task in .dev/task-*.md
and injects it as a continuation prompt — driving autonomous sequential
implementation until the roadmap is done.

Exit codes:
  0  — allow stop (all tasks done, or blocked on research)
  Non-zero with JSON on stdout — block stop and inject next task prompt

Output format (on block):
  {"decision": "block", "reason": "<prompt for Claude>"}
"""

import json
import os
import re
import sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
TASKS_DIR = REPO_ROOT / ".dev"
MAX_BLOCKS = int(os.environ.get("ROADMAP_MAX_BLOCKS", "0"))  # 0 = unlimited
STATE_FILE = REPO_ROOT / ".claude" / "roadmap-hook-state.json"

# Milestones to actively pursue (skip deferred unless all others done)
ACTIVE_MILESTONES = {0, 1, 2, 3, 4, 5}
DEFERRED_MILESTONES = {"deferred"}

# ── Task parsing ──────────────────────────────────────────────────────────────

def parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter fields from a task file (no yaml dep required)."""
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm_text = m.group(1)
    result = {}

    # Simple line-by-line parse for the fields we need
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not key or key.startswith("-"):
            continue

        # List fields
        if val == "" or val == "[]":
            result[key] = []
        elif val.startswith("["):
            # Inline list: [task-001, task-002]
            items = re.findall(r"[\w-]+", val)
            result[key] = items
        else:
            result[key] = val.strip('"').strip("'")

    # Handle multi-line list fields (depends_on, blocks, parallel_with)
    for field in ("depends_on", "blocks", "parallel_with", "research_questions"):
        block_m = re.search(
            rf"^{field}:\s*\n((?:  - .+\n?)*)",
            fm_text,
            re.MULTILINE,
        )
        if block_m:
            items = re.findall(r"- (.+)", block_m.group(1))
            result[field] = [i.strip().strip('"').strip("'") for i in items]

    return result


def load_all_tasks() -> dict[str, dict]:
    """Return {task_id: frontmatter_dict} for all task files."""
    tasks = {}
    for path in sorted(TASKS_DIR.glob("task-*.md")):
        fm = parse_frontmatter(path)
        task_id = fm.get("id") or path.stem
        fm["_path"] = str(path)
        tasks[task_id] = fm
    return tasks


# ── State tracking ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"blocks": 0, "last_task": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Task selection ─────────────────────────────────────────────────────────────

PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}

def find_next_task(tasks: dict[str, dict]) -> dict | None:
    """
    Find the highest-priority unblocked ready task.
    A task is eligible if:
      - status == "ready"
      - milestone is in ACTIVE_MILESTONES (int) or all active tasks done
      - all depends_on tasks have status == "done"
    """
    done_ids = {tid for tid, t in tasks.items() if t.get("status") == "done"}

    candidates = []
    for tid, task in tasks.items():
        status = task.get("status", "")
        if status != "ready":
            continue

        # Skip deferred milestone tasks unless everything else is done
        milestone = task.get("milestone", "deferred")
        try:
            ms_int = int(milestone)
        except (ValueError, TypeError):
            ms_int = None

        if ms_int is None:
            # Deferred — only include if all active tasks are done
            active_remaining = [
                t for t in tasks.values()
                if t.get("status") not in ("done", "needs-research")
                and t.get("milestone") not in DEFERRED_MILESTONES
                and t.get("id") != tid
            ]
            if active_remaining:
                continue
        elif ms_int not in ACTIVE_MILESTONES:
            continue

        # Check all depends_on are done
        deps = task.get("depends_on", [])
        if isinstance(deps, str):
            deps = [deps] if deps else []
        if not all(d in done_ids for d in deps):
            continue

        priority = PRIORITY_ORDER.get(task.get("priority", "p3"), 3)
        candidates.append((priority, ms_int or 99, tid, task))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][3]


# ── Documentation check ────────────────────────────────────────────────────────

def check_docs_current(tasks: dict) -> list[str]:
    """
    Return list of documentation gaps if milestone 0 tasks are all done.
    These are included in the continuation prompt when relevant.
    """
    gaps = []
    m0_tasks = [t for t in tasks.values() if str(t.get("milestone", "")) == "0"]
    m0_done = all(t.get("status") == "done" for t in m0_tasks)

    if not m0_done:
        return gaps  # doc check deferred until milestone 0 complete

    readme = REPO_ROOT / "README.md"
    claude_md = REPO_ROOT / "CLAUDE.md"
    docs_dir = REPO_ROOT / "docs"

    if readme.exists():
        content = readme.read_text()
        if "space create" not in content:
            gaps.append("README.md missing `iobox space` quickstart")
        if "google_calendar" not in content and "calendar" not in content.lower():
            gaps.append("README.md missing calendar/drive provider docs")
    else:
        gaps.append("README.md does not exist")

    if claude_md.exists():
        content = claude_md.read_text()
        if "CalendarProvider" not in content:
            gaps.append("CLAUDE.md missing CalendarProvider architecture section")
        if "space_config" not in content and "SpaceConfig" not in content:
            gaps.append("CLAUDE.md missing space_config module description")

    workspace_doc = docs_dir / "workspace-guide.md"
    if not workspace_doc.exists():
        gaps.append("docs/workspace-guide.md missing")

    return gaps


# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_prompt(task: dict, state: dict, doc_gaps: list[str]) -> str:
    tid = task.get("id", "unknown")
    title = task.get("title", "")
    milestone = task.get("milestone", "?")
    priority = task.get("priority", "?")
    effort = task.get("estimated_effort", "?")
    path = task.get("_path", f".dev/{tid}.md")
    # Make path relative
    try:
        path = str(Path(path).relative_to(REPO_ROOT))
    except ValueError:
        pass

    blocks_so_far = state.get("blocks", 0)

    lines = [
        f"## Roadmap task ready: {tid} — {title}",
        f"",
        f"Milestone: {milestone} | Priority: {priority} | Effort: {effort}",
        f"(Session continuation #{blocks_so_far + 1})",
        f"",
        f"Read `{path}` for full implementation instructions, then implement the task completely:",
        f"",
        f"1. Implement all files listed in the task's **Files** table",
        f"2. Write all tests described in **Test Strategy** and verify they pass (`make test`)",
        f"3. Run `make check` (lint + type-check + tests) — fix all failures before marking done",
        f"4. Update documentation if the task affects user-facing behaviour:",
        f"   - `CLAUDE.md` — architecture notes, key invariants, new modules",
        f"   - `README.md` — if new CLI commands or install steps are needed",
        f"   - `docs/` — if new provider or feature guide is needed",
        f"5. Mark the task complete by updating its frontmatter: `status: done`",
        f"",
        f"**Definition of Done** (all must be true before marking done):",
        f"- [ ] All files in the task's Files table exist and match the spec",
        f"- [ ] `make test` passes with no failures or skips on new tests",
        f"- [ ] `make type-check` passes with no new errors",
        f"- [ ] `make lint` passes",
        f"- [ ] Task frontmatter updated to `status: done`",
    ]

    if doc_gaps:
        lines += [
            f"",
            f"**Documentation gaps detected** (fix these too):",
        ]
        for gap in doc_gaps:
            lines.append(f"- {gap}")

    lines += [
        f"",
        f"When fully done, stop — the roadmap hook will automatically queue the next task.",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    tasks = load_all_tasks()

    if not tasks:
        # No task files found — silent pass
        sys.exit(0)

    state = load_state()
    blocks = state.get("blocks", 0)

    # Respect MAX_BLOCKS if set
    if MAX_BLOCKS > 0 and blocks >= MAX_BLOCKS:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"ROADMAP_MAX_BLOCKS={MAX_BLOCKS} reached ({blocks} sessions run). "
                f"Stopping autonomous loop. Review progress with `cat .dev/task-*.md | grep 'status:'`."
            )
        }))
        # Don't increment — let user reset
        sys.exit(0)

    # Check documentation gaps (only relevant post-milestone-0)
    doc_gaps = check_docs_current(tasks)

    # Find next task
    next_task = find_next_task(tasks)

    if next_task is None:
        # Check if there are needs-research or blocked tasks remaining
        remaining = [
            t for t in tasks.values()
            if t.get("status") not in ("done",)
            and str(t.get("milestone", "deferred")) not in DEFERRED_MILESTONES
        ]
        if remaining:
            statuses = ", ".join(
                f"{t.get('id')} ({t.get('status')})" for t in remaining[:5]
            )
            # Still tasks left but none are ready — blocked or needs-research
            sys.stdout.write(json.dumps({
                "decision": "block",
                "reason": (
                    f"No 'ready' tasks found. Remaining tasks: {statuses}.\n\n"
                    f"Review blocked tasks — their dependencies may now be satisfied. "
                    f"Update any task whose depends_on are all `done` to `status: ready`, "
                    f"then the hook will automatically pick it up."
                )
            }))
            sys.exit(0)
        else:
            # All done — allow Claude to stop normally.
            # The completion message was already shown in a prior session.
            sys.exit(0)

    # Found a task — block stop and inject prompt
    prompt = build_prompt(next_task, state, doc_gaps)

    state["blocks"] = blocks + 1
    state["last_task"] = next_task.get("id")
    save_state(state)

    sys.stdout.write(json.dumps({"decision": "block", "reason": prompt}))
    sys.exit(0)


if __name__ == "__main__":
    main()
