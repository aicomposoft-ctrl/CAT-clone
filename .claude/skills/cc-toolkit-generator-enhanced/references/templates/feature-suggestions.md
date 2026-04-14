# Feature Suggestions System Templates

Templates for generating a feature navigation and contextual suggestion system.
Combines CLAUDE.md roadmap, SessionStart hook for dynamic context, `/next` command,
and `feature-navigator` skill for on-demand roadmap navigation.

Architecture: **feature-roadmap.json** as single source of truth → consumed by hook, skill, and command.

---

## 1. Data File Template: `feature-roadmap.json`

Generate as `.claude/feature-roadmap.json` — pre-populate from project's PRD/Specification:

```json
{
  "project": "{{PROJECT_NAME}}",
  "current_sprint": "{{SPRINT_NAME}}",
  "features": [
    {
      "id": "{{feature-id}}",
      "name": "{{Feature Name}}",
      "description": "{{Brief description of the feature}}",
      "status": "done|in_progress|next|planned|blocked",
      "files": ["src/path/to/main-file.ts"],
      "depends_on": ["{{other-feature-id}}"],
      "sprint": "{{SPRINT_NAME}}"
    }
  ]
}
```

**Status values:**
- `done` — completed and verified
- `in_progress` — currently being worked on
- `next` — highest priority, ready to start
- `planned` — in backlog, not yet prioritized
- `blocked` — waiting on dependency or external factor

**Population rules:**
- Extract features from PRD.md Functional Requirements
- Extract dependencies from Architecture.md
- Set initial statuses based on Specification.md priorities (MoSCoW)
- Must-have features → `next`, Should-have → `planned`
- Pre-populate `files` from Pseudocode.md or Architecture.md when possible

---

## 2. Hook Template: SessionStart Event

Add to `.claude/settings.json` hooks section alongside existing hooks:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/hooks/feature-context.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Generate as `.claude/hooks/feature-context.py`:

```python
#!/usr/bin/env python3
"""
Injects dynamic feature context at the start of each Claude Code session.
stdout on SessionStart is added as context that Claude sees.

Reads feature-roadmap.json + git log + TODO scan to build a context snapshot.
"""
import json
import subprocess
import sys
from pathlib import Path


def get_recent_changes():
    """Analyze git log to understand recent progress."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5", "--no-decorate"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_open_todos():
    """Find TODO/FIXME/HACK in source code."""
    try:
        result = subprocess.run(
            ["grep", "-rn", r"TODO\|FIXME\|HACK", "src/",
             "--include=*.py", "--include=*.ts", "--include=*.js",
             "--include=*.tsx", "--include=*.jsx", "--include=*.go",
             "--include=*.rs", "-l"],
            capture_output=True, text=True, timeout=5
        )
        files = [f for f in result.stdout.strip().split('\n') if f]
        return files[:5]
    except Exception:
        return []


def load_roadmap():
    """Load feature roadmap from project config."""
    roadmap_path = Path(".claude/feature-roadmap.json")
    if roadmap_path.exists():
        with open(roadmap_path) as f:
            return json.load(f)
    return None


def format_sprint_progress(features, sprint_name):
    """Calculate sprint completion percentage."""
    sprint_features = [f for f in features if f.get("sprint") == sprint_name]
    if not sprint_features:
        return ""
    done = sum(1 for f in sprint_features if f.get("status") == "done")
    total = len(sprint_features)
    pct = int(done / total * 100)
    return f"SPRINT PROGRESS: {sprint_name} — {done}/{total} ({pct}%)"


def main():
    roadmap = load_roadmap()
    recent = get_recent_changes()
    todos = get_open_todos()

    parts = []
    parts.append("=== PROJECT FEATURE CONTEXT ===")

    if roadmap:
        features = roadmap.get("features", [])
        sprint = roadmap.get("current_sprint", "")

        # Sprint progress
        progress = format_sprint_progress(features, sprint)
        if progress:
            parts.append(progress)

        # Currently building
        in_progress = [f for f in features if f.get("status") == "in_progress"]
        for f in in_progress[:2]:
            files = ", ".join(f.get("files", []))
            parts.append(
                f"CURRENTLY BUILDING: {f['name']} — {f.get('description', '')}"
                + (f" [files: {files}]" if files else "")
            )

        # Suggested next
        next_up = [f for f in features if f.get("status") == "next"]
        for f in next_up[:2]:
            parts.append(
                f"SUGGESTED NEXT: {f['name']} — {f.get('description', '')}"
            )

        # Blocked items
        blocked = [f for f in features if f.get("status") == "blocked"]
        for f in blocked[:2]:
            deps = ", ".join(f.get("depends_on", []))
            parts.append(f"BLOCKED: {f['name']} — waiting on: {deps}")

    if recent:
        parts.append(f"RECENT COMMITS:\n{recent}")

    if todos:
        parts.append(f"FILES WITH TODOs: {', '.join(todos)}")

    parts.append("=== END CONTEXT ===")

    # stdout on SessionStart → Claude sees as context
    print('\n'.join(parts))


if __name__ == "__main__":
    main()
```

**How it works:**
- On every session start, Claude receives a context snapshot: current progress, what to work on next, blockers, recent git history, TODOs
- The built-in Prompt Suggestion Generator v2 (Tab-completion) sees this context and generates more relevant suggestions
- Zero token cost during work — only runs once at session start

---

## 3. Hook Template: Stop Event — Auto-Commit Roadmap

Add to `.claude/settings.json` hooks section (alongside existing Stop hooks):

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash -c 'if [ -f \".claude/feature-roadmap.json\" ] && git diff --name-only -- \".claude/feature-roadmap.json\" 2>/dev/null | grep -q .; then git add .claude/feature-roadmap.json && git commit -m \"docs(roadmap): update feature status\" && echo \"✅ feature-roadmap.json auto-committed\"; fi'"
          }
        ]
      }
    ]
  }
}
```

**What it does:** If Claude updated feature-roadmap.json during the session (marking features as done, changing statuses), it auto-commits the change.

---

## 4. Skill Template: `feature-navigator`

Generate as `.claude/skills/feature-navigator/SKILL.md`:

````markdown
---
name: feature-navigator
description: >
  Navigate project features and suggest next steps. Use when the user
  asks "what's next", "what should I work on", "show roadmap", starts a new task,
  or when a feature is completed. Also trigger on "roadmap", "backlog",
  "sprint", "feature status", or "что делать дальше".
---

# Feature Navigator

Read `.claude/feature-roadmap.json` for current feature status, then present:

## Step 1: Gather Context

1. Read `.claude/feature-roadmap.json`
2. Run `git log --oneline -10` for recent progress
3. Scan for TODO/FIXME: `grep -rn "TODO\|FIXME" src/ --include="*.ts" --include="*.py" -l | head -5`

## Step 2: Present Current State

```
═══════════════════════════════════════════════════════════
📋 Feature Roadmap: [Project Name]
   Sprint: [Sprint Name] — [N/M] complete ([X]%)
═══════════════════════════════════════════════════════════

🔨 In Progress:
   • [Feature Name] — [description]
     Files: [file paths]

⏭️ Next Up:
   • [Feature Name] — [description]
     Depends on: [none | feature-id]

🚫 Blocked:
   • [Feature Name] — waiting on: [dependency]

📝 TODOs Found:
   • [file:line] — [TODO text]

🕐 Recent Work:
   [git log last 5 commits]
═══════════════════════════════════════════════════════════
```

## Step 3: Suggest Top 3 Actions

Format as numbered list, each 3-8 words:
1. **[Feature/Task Name]** — Brief actionable description. Files: `path/to/files`
2. **[Bug/TODO]** — From code scan. Location: `file:line`
3. **[Follow-up]** — Based on recent progress

## Step 4: Ask

```
Which one shall we tackle? (1/2/3 or describe your own)
```

## Updating Roadmap

When a feature is completed during the session:
1. Update its status to `"done"` in `.claude/feature-roadmap.json`
2. If there are features with `"depends_on"` pointing to the completed feature,
   check if all their dependencies are now done → update to `"next"`
3. Inform the user: `✅ [Feature] marked as done. [Next Feature] is now unblocked.`

## Priority Rules

- `blocked` items → show but don't suggest (explain what's blocking)
- `in_progress` → suggest continuing (highest priority)
- `next` → suggest starting (second priority)
- `planned` → only suggest if no `next` items remain
- Respect `depends_on` — never suggest a feature whose dependencies aren't `done`

## Important

- Keep suggestions actionable and specific (3-8 words each)
- After presenting, always ask which task to start
- If all features are `done`, congratulate and suggest: refactoring, test coverage, documentation, or performance optimization
````

---

## 5. Command Template: `/next`

Generate as `.claude/commands/next.md`:

````markdown
---
description: Show next features to work on from the project roadmap.
  Quick overview of sprint progress and top suggested tasks.
  $ARGUMENTS: optional — "update" to refresh statuses, or feature-id to mark as done
---

# /next $ARGUMENTS

## Default: Show Next Steps

1. Read `.claude/feature-roadmap.json`
2. Show current sprint progress (% complete)
3. List top 3 suggested next tasks based on priority and dependencies
4. Show any blocking issues
5. Ask which task to start

Format as a brief, actionable list.

## /next update

Review the current codebase state and conversation history:
1. Check which features appear to be implemented (scan for key files)
2. Suggest status updates for features that may be done
3. Apply updates after user confirmation

## /next [feature-id]

Mark a specific feature as done:
1. Update status to `"done"` in `.claude/feature-roadmap.json`
2. Check if this unblocks any dependent features → update to `"next"`
3. Show updated sprint progress
4. Suggest the next feature to work on
````

---

## 6. CLAUDE.md Integration

When generating CLAUDE.md, include this section:

```markdown
## 📋 Feature Roadmap
Roadmap: [.claude/feature-roadmap.json](.claude/feature-roadmap.json) — single source of truth for feature status.
Sprint progress and next steps are injected automatically at session start.
Quick check: `/next` | Full overview: ask "what should I work on?"
Mark done: `/next [feature-id]` | Update all: `/next update`
```

The SessionStart hook injects dynamic context automatically, improving Tab-completion suggestions.

---

## 7. DEVELOPMENT_GUIDE.md Integration

Add to the development workflow section:

```markdown
## Feature Workflow

1. Run `/next` to see current sprint status and suggested tasks
2. Pick a feature to work on → it appears as "in_progress" in roadmap
3. Implement using `/feature [name]` or `/feature-ent [name]` lifecycle
4. When done → `/next [feature-id]` to mark complete and see what's next
5. Feature roadmap auto-commits on session end (Stop hook)

The SessionStart hook gives Claude context about your current progress,
so Tab-completion suggestions are aligned with your roadmap.
```

---

## Generation Rules

**When populating feature-roadmap.json from project docs:**

| Source Document | What to Extract |
|----------------|----------------|
| PRD.md | Feature names, descriptions, MoSCoW priorities |
| Specification.md | User stories → features, acceptance criteria |
| Architecture.md | File paths, dependencies between components |
| Pseudocode.md | Key files per feature |
| Completion.md | Sprint/phase structure |

**Status assignment:**
- Features already implemented (from git/codebase scan) → `done`
- Feature from current sprint, highest priority → `in_progress` (max 1-2)
- Next Must-have features → `next`
- Should-have features → `planned`
- Features with unmet `depends_on` → `blocked`

**Minimum viable roadmap:** At least 5 features with correct statuses and dependencies.

---

## Integration with /feature and /feature-ent

The feature-suggestions system complements the feature lifecycle:

```
/next                    → "What should I work on?"
                                ↓
/feature [name]          → Plan + Validate + Implement + Review (simple features)
/feature-ent [name]      → Same but with DDD/ADR/C4 (complex features)
                                ↓
/next [feature-id]       → Mark done, see what's next
```

The `/next` command is the **discovery** layer, while `/feature` and `/feature-ent` are the **execution** layer.
