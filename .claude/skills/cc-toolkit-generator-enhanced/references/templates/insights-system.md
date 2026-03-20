# Insights System Templates

Templates for generating the insights knowledge base system.
Architecture: **index file + individual detail files** (like llms.txt pattern).

---

## 1. Command Template: `/myinsights`

Generate as `.claude/commands/myinsights.md`:

````markdown
---
description: Capture a development insight or manage existing insights.
  Creates structured entry in myinsights/ folder with auto-indexing.
  $ARGUMENTS: brief title OR subcommand (archive INS-NNN, status INS-NNN [active|workaround|obsolete])
---

# /myinsights $ARGUMENTS

## What You Do

Manage the project's living knowledge base in `myinsights/` folder.
Each insight is stored as an individual file for precise context loading.

## Subcommands

- `/myinsights [title]` — capture a new insight (default)
- `/myinsights archive INS-NNN` — move insight to archive (obsolete)
- `/myinsights status INS-NNN [active|workaround|obsolete]` — change insight status

## Capture Flow (default)

### Step 0. Duplicate Detection

**BEFORE creating a new insight**, search the index for duplicates:

1. Read `myinsights/1nsights.md`
2. Search the `Error Signatures` column for matching error strings from the current issue
3. Search the `Summary` column for semantically similar descriptions

**If potential duplicate found:**
```
⚠️ Possible duplicate of [INS-NNN] Title
   File: myinsights/INS-NNN-slug.md
   
   Options:
   1. View existing insight and update it with new info
   2. Create new insight anyway (different root cause)
   3. Cancel
```

If the user chooses to update — append new info to the existing detail file under
a `### Update YYYY-MM-DD` subsection and update the index entry if needed.

### Step 1. Collect Information

Ask the user (or reconstruct from conversation context) these details:

- **Title:** One-line summary of the problem/finding
- **Error Signatures:** Exact error strings, codes, or exception names that can be grepped
  (e.g., `ECONNREFUSED`, `P1001`, `TypeError: Cannot read properties of undefined`)
- **Symptoms:** What went wrong? What was the unexpected behavior?
- **Diagnostic Steps:** What steps were taken to identify the root cause?
- **Root Cause:** What was the actual underlying problem?
- **Solution:** What fixed it? Step-by-step resolution.
- **Prevention:** How to avoid this in the future? Any guards, tests, or checks to add?
- **Tags:** Relevant categories (e.g., `docker`, `auth`, `deployment`, `database`, `config`)
- **Related:** Links to other insights, docs, or issues (e.g., `INS-003`, `INS-017`)

### Step 2. Create Individual Detail File

**File naming:** `myinsights/INS-NNN-slug.md` where slug is a short kebab-case description.

```markdown
# [INS-NNN] Title

**Date:** YYYY-MM-DD
**Status:** 🟢 Active | 🟡 Workaround | 🔴 Obsolete
**Severity:** 🔴 Critical / 🟡 Medium / 🟢 Low
**Tags:** `tag1`, `tag2`, `tag3`
**Hits:** 0

## Error Signatures
```
EXACT_ERROR_STRING_1
EXACT_ERROR_STRING_2
error code or exception name
```

## Symptoms
[What went wrong — error messages, unexpected behavior, failing tests]

## Diagnostic Steps
1. [What was checked first]
2. [What was tried]
3. [What led to the root cause]

## Root Cause
[The actual underlying problem — be specific]

## Solution
1. [Step-by-step fix]
2. [Code changes, config changes]
3. [Verification that it works]

## Prevention
- [How to avoid this in the future]
- [Tests to add, checks to implement]

## Related
- [INS-XXX](INS-XXX-slug.md) — related insight description
- [Link to external doc or issue]
```

### Step 3. Update Index (`myinsights/1nsights.md`)

If `myinsights/1nsights.md` doesn't exist, create it:

```markdown
# 🔍 Development Insights Index

Living knowledge base. **Read this file first** — then load specific detail files as needed.

> **For Claude Code:** When you encounter an error, `grep` the Error Signatures column below.
> If you find a match, read ONLY the linked detail file — don't load everything.

| ID | Error Signatures | Summary | Status | Hits | File |
|----|-----------------|---------|--------|------|------|
```

Then append a new row:

```markdown
| INS-NNN | `ERROR_SIG_1`, `ERROR_SIG_2` | One-line summary | 🟢 Active | 0 | [INS-NNN-slug.md](INS-NNN-slug.md) |
```

### Step 4. Auto-numbering

List existing `INS-*.md` files in `myinsights/` (including `archive/`),
find the highest `INS-NNN` number, increment by 1. First entry is `INS-001`.

### Step 5. Notify

After saving:
```
✅ Insight captured: [INS-NNN] Title
📄 myinsights/INS-NNN-slug.md created
📋 myinsights/1nsights.md index updated
🔄 Will be auto-committed on session end (Stop hook)
```

If this is the FIRST insight in the project, also notify:
```
📌 myinsights/ reference added to CLAUDE.md as knowledge source
```

## Archive Flow (`/myinsights archive INS-NNN`)

1. Move `myinsights/INS-NNN-slug.md` → `myinsights/archive/INS-NNN-slug.md`
2. Update status in `1nsights.md` index to `🔴 Obsolete`
3. Add `(archived)` suffix to the file link in index
4. Notify: `📦 INS-NNN archived → myinsights/archive/`

## Status Flow (`/myinsights status INS-NNN [status]`)

1. Update `**Status:**` line in the detail file
2. Update status column in `1nsights.md` index
3. If new status is `obsolete` — suggest archiving: `💡 Consider: /myinsights archive INS-NNN`
4. Notify: `🔄 INS-NNN status → [new status]`

## Hit Counter

When an insight is used to solve a problem (matched via grep or manual lookup):
1. Increment `**Hits:**` counter in the detail file
2. Increment `Hits` column in `1nsights.md` index
3. Note: `📊 INS-NNN hit count → N (helped solve current issue)`

Insights with higher hit counts are more valuable — consider this when prioritizing
which insights to check first during debugging.
````

---

## 2. Rule Template: `insights-capture.md`

Generate as `.claude/rules/insights-capture.md`:

````markdown
# Insights Capture Protocol

## 🔍 Error-First Lookup (CRITICAL — do this BEFORE debugging)

**IMPORTANT:** When you encounter ANY error, ALWAYS do this before starting to debug:

```bash
# Step 1: Check if index exists
if [ -f "myinsights/1nsights.md" ]; then
  # Step 2: Grep for the error signature in the index
  grep -i "ERROR_STRING_OR_CODE" myinsights/1nsights.md
fi
```

**Pattern:**
1. User reports a problem or an error occurs
2. Extract the key error string (error code, exception name, or unique message fragment)
3. `grep` the error string against `myinsights/1nsights.md` Error Signatures column
4. **If match found** → read ONLY the linked detail file → suggest documented solution FIRST
5. **If match found AND solution works** → increment hit counter in both index and detail file
6. **If no match** → debug normally → after resolution, suggest capturing with `/myinsights`

**Example lookup flow:**
```
Error: ECONNREFUSED 127.0.0.1:5432
→ grep "ECONNREFUSED" myinsights/1nsights.md
→ Match: INS-001 | `ECONNREFUSED`, `port 5432` | Postgres in Docker... | INS-001-docker-pg-network.md
→ cat myinsights/INS-001-docker-pg-network.md
→ Apply documented solution
→ Increment hit counter
```

## When to Suggest Capturing an Insight

Proactively suggest `/myinsights` when ANY of these occur:

1. **Error → Fix cycle**: A non-trivial bug was debugged and resolved
   - Especially: errors that took >3 attempts to fix
   - Especially: misleading error messages that pointed wrong direction

2. **Configuration surprise**: A config setting behaved unexpectedly
   - Docker networking quirks
   - Environment variable gotchas
   - Build tool configuration issues

3. **Dependency issue**: A library/package caused problems
   - Version conflicts
   - Undocumented breaking changes
   - Platform-specific behavior

4. **Architecture decision under pressure**: A design choice was made
   during debugging that should be documented

5. **Workaround applied**: A temporary fix was applied that needs
   future attention (suggest status: 🟡 Workaround)

## How to Suggest

After resolving a tricky issue, say:
```
💡 This looks like a valuable insight. Want me to capture it?
   Run `/myinsights [brief title]` or say "да, запиши"
```

## When NOT to Suggest

- Trivial typos or syntax errors
- Well-known framework patterns
- Issues already documented in `myinsights/` (check index first!)
- User explicitly said they don't want to capture

## Lifecycle Awareness

When reviewing insights during lookup, check the status:
- `🟢 Active` — trusted solution, apply directly
- `🟡 Workaround` — temporary fix, may need better solution. Apply but flag to user.
- `🔴 Obsolete` — should be in archive. If found in main folder, suggest `/myinsights archive INS-NNN`

When a workaround gets a proper fix, suggest:
```
💡 INS-NNN was a workaround. Now we have a proper fix — update it?
   Run `/myinsights status INS-NNN active` and I'll update the solution.
```
````

---

## 3. Hook Template: Stop Event

Add to `.claude/settings.json` hooks section:

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "command": "bash -c '\nDIR=\"myinsights\"\nINDEX=\"myinsights/1nsights.md\"\nCLAUDE=\"CLAUDE.md\"\n\n# Check if myinsights/ has any uncommitted changes\nif [ -d \"$DIR\" ] && (git diff --name-only -- \"$DIR\" 2>/dev/null | grep -q . || git diff --name-only --cached -- \"$DIR\" 2>/dev/null | grep -q . || git ls-files --others --exclude-standard -- \"$DIR\" 2>/dev/null | grep -q .); then\n  \n  # Auto-add insights reference to CLAUDE.md on first time\n  if ! grep -q \"myinsights\" \"$CLAUDE\" 2>/dev/null; then\n    printf \"\\n## 🔍 Development Insights (живая база знаний)\\nIndex: [myinsights/1nsights.md](myinsights/1nsights.md) — check here FIRST before debugging.\\n⚠️ On error → grep the error string in the index → read only the matched detail file.\\nCapture new findings: \\`/myinsights [title]\\`\\n\" >> \"$CLAUDE\"\n    git add \"$CLAUDE\"\n    echo \"📌 myinsights/ reference added to CLAUDE.md\"\n  fi\n  \n  # Auto-commit all changes in myinsights/\n  git add \"$DIR\"\n  git commit -m \"docs(insights): update knowledge base\"\n  echo \"✅ myinsights/ auto-committed\"\nfi\n'"
      }
    ]
  }
}
```

**Readable version:**

```bash
#!/bin/bash
DIR="myinsights"
INDEX="myinsights/1nsights.md"
CLAUDE="CLAUDE.md"

# Check if myinsights/ has any uncommitted or untracked changes
if [ -d "$DIR" ] && \
   (git diff --name-only -- "$DIR" 2>/dev/null | grep -q . || \
    git diff --name-only --cached -- "$DIR" 2>/dev/null | grep -q . || \
    git ls-files --others --exclude-standard -- "$DIR" 2>/dev/null | grep -q .); then
  
  # Auto-add insights reference to CLAUDE.md on first time
  if ! grep -q "myinsights" "$CLAUDE" 2>/dev/null; then
    cat >> "$CLAUDE" << 'EOF'

## 🔍 Development Insights (живая база знаний)
Index: [myinsights/1nsights.md](myinsights/1nsights.md) — check here FIRST before debugging.
⚠️ On error → grep the error string in the index → read only the matched detail file.
Capture new findings: `/myinsights [title]`
EOF
    git add "$CLAUDE"
    echo "📌 myinsights/ reference added to CLAUDE.md"
  fi
  
  # Auto-commit all changes in myinsights/
  git add "$DIR"
  git commit -m "docs(insights): update knowledge base"
  echo "✅ myinsights/ auto-committed"
fi
```

**Why `Stop` event:**
- Non-intrusive — doesn't interrupt work flow
- Catches ALL changes in `myinsights/` — new files, edits, hit counter updates, archives
- Handles **untracked** new files (the old version only caught modified tracked files)
- Ensures the entire knowledge base folder is always committed
- First-time CLAUDE.md update happens seamlessly

---

## 4. CLAUDE.md Integration

When generating CLAUDE.md, ALWAYS include this section (even before first insight exists):

```markdown
## 🔍 Development Insights (живая база знаний)
Index: [myinsights/1nsights.md](myinsights/1nsights.md) — check here FIRST before debugging.
⚠️ On error → grep the error string in the index → read only the matched detail file.
Capture new findings: `/myinsights [title]`
```

The Stop hook will add this section automatically if it's missing (safety net), but generating
it upfront ensures Claude Code reads insights from the very first session.
