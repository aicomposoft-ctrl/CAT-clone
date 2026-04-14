# Hook: SessionStart JSON Context Injection

**Category:** Hook
**Maturity:** 🔴 Alpha
**Source:** CAT (.claude/settings.json), 2026-04-05

---

## What It Does

Reads a JSON file on session start and injects a formatted summary into the
Claude Code context. Used to surface current sprint status, active tasks,
or project state at the beginning of each conversation.

## When to Use

- Injecting sprint/roadmap context from a tracked JSON file
- Surfacing "what's in progress" at the start of each session
- Any project state that fits in a JSON file and is useful as context

## When NOT to Use

- Large context documents (use CLAUDE.md or docs/ instead)
- Secrets or credentials (never inject via hooks)
- Context that changes mid-session (hooks only fire at start)

## Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "cat {{JSON_FILE_PATH}} 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); {{EXTRACTION_LOGIC}}\" 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

## Template: Sprint Context Injection

Reads `.claude/feature-roadmap.json` and prints active sprint summary:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "cat .claude/feature-roadmap.json 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); sprints=[s for s in d.get('sprints',[]) if s.get('status')=='active']; print('\\n=== SPRINT CONTEXT ==='); [print(f\\\"Sprint: {s['name']} | {len([f for f in s.get('features',[]) if f.get('status')=='in-progress'])} in-progress, {len([f for f in s.get('features',[]) if f.get('status')=='todo'])} todo\\\") for s in sprints]; print('Run /next for full details\\n')\" 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

## JSON File Format (feature-roadmap.json)

```json
{
  "sprints": [
    {
      "name": "Sprint 1",
      "status": "active",
      "features": [
        { "id": "auth", "name": "Authentication", "status": "done" },
        { "id": "sku-crud", "name": "SKU CRUD", "status": "in-progress" },
        { "id": "scraper", "name": "WB Scraper", "status": "todo" }
      ]
    }
  ]
}
```

## Gotchas

- `|| true` at the end ensures the session starts even if the JSON file doesn't exist.
- `2>/dev/null` hides Python parsing errors from the session output.
- The injected text appears once at session start — it does NOT re-inject mid-session.
- Keep the output short (1-3 lines) — long hook output clutters the session start.

## Variants

### Variant B: Inject from any key-value file

```bash
cat project-status.txt 2>/dev/null | head -5 || true
```

### Variant C: Git log as context

```bash
echo "=== RECENT COMMITS ===" && git log --oneline -5 2>/dev/null || true
```

## Related Artifacts

- `hooks/danger-command-blocker.md`
