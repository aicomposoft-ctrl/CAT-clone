# Hook: Danger Command Blocker (PreToolUse)

**Category:** Hook
**Maturity:** 🔴 Alpha
**Source:** CAT (.claude/settings.json), 2026-04-05

---

## What It Does

Blocks dangerous bash command patterns before execution in Claude Code.
Applies as a `PreToolUse` hook on the `Bash` tool.

Blocked patterns:
- `rm -rf` targeting non-/tmp paths
- `git push --force origin main` / `master`
- `DROP TABLE`
- `DELETE FROM table ;` (unqualified delete)

## When to Use

Any Claude Code project where you want a safety net against accidental destructive commands,
especially in autonomous / less-supervised execution modes (`/run`, `/go`).

## Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$CLAUDE_TOOL_INPUT\" | python3 -c \"import sys,json,re; inp=json.load(sys.stdin); cmd=inp.get('command',''); patterns=[r'rm\\s+-rf\\s+[^/tmp]', r'git\\s+push\\s+--force\\s+origin\\s+main', r'git\\s+push\\s+--force\\s+origin\\s+master', r'DROP\\s+TABLE', r'DELETE\\s+FROM\\s+\\w+\\s*;']; found=[p for p in patterns if re.search(p, cmd, re.IGNORECASE)]; [print(f'BLOCKED: Dangerous command pattern detected: {p}') or sys.exit(1) for p in found]\" 2>/dev/null || true"
          }
        ]
      }
    ]
  }
}
```

## Extending the Block List

Edit the `patterns` list in the command to add more patterns:

```python
patterns = [
    r'rm\s+-rf\s+[^/tmp]',                         # rm -rf (non-tmp)
    r'git\s+push\s+--force\s+origin\s+main',        # force push main
    r'git\s+push\s+--force\s+origin\s+master',      # force push master
    r'DROP\s+TABLE',                                 # DROP TABLE
    r'DELETE\s+FROM\s+\w+\s*;',                     # unqualified DELETE
    r'truncate\s+table',                             # TRUNCATE TABLE
    r'kubectl\s+delete\s+namespace',                 # k8s namespace delete
    r'terraform\s+destroy\s+--auto-approve',         # terraform destroy
]
```

## Gotchas

- The `|| true` at the end prevents the hook itself from crashing if `python3` fails.
  This means if Python is unavailable, the hook silently passes (fail-open, not fail-closed).
  For stricter security, remove `|| true`.
- `[^/tmp]` in the rm pattern uses a character class negation — `rm -rf /tmp/something`
  is allowed; `rm -rf /var/data` is blocked.
- The `2>/dev/null` suppresses python errors from appearing in output.

## Alternatives

For git-specific protection only:
```json
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "echo \"$CLAUDE_TOOL_INPUT\" | python3 -c \"import sys,json; inp=json.load(sys.stdin); cmd=inp.get('command',''); 'push --force origin main' in cmd and (print('BLOCKED: Force push to main') or sys.exit(1))\""
  }]
}
```

## Related Artifacts

- `hooks/session-start-context-injection.md`
