# Phase 3: Decontextualize

Transform project-specific artifacts into reusable, documented toolkit entries.

## Goal

Each classified artifact must be generalized so it works in ANY project,
not just the one it was extracted from. This is the critical step that separates
"copying code" from "building a toolkit."

## The 3-Step Decontextualization

### Step 1: Remove Project Specifics

**Find and replace:**

| Project-Specific | Generalized Replacement |
|-----------------|----------------------|
| Concrete service names (`auth-service`) | `{{SERVICE_NAME}}` or generic (`service`) |
| Specific paths (`src/auth/errors.rs`) | Pattern description ("error handling module") |
| Hardcoded configs (`port: 3000`) | Parameters (`port: {{PORT}}`) |
| Specific DB names/tables | Generic schema references |
| API endpoint paths (`/api/v1/users`) | `{{API_PREFIX}}/{{RESOURCE}}` |
| Company/product names | `{{PROJECT_NAME}}` |
| Specific env variables | Documented parameter list |
| Concrete user models | Interface/trait with required methods |

**Example transformation:**

Before (project-specific):
```rust
// auth-service/src/middleware/rate_limit.rs
pub fn rate_limit(config: &AuthConfig) -> RateLimiter {
    RateLimiter::new(config.max_requests, config.window_secs)
}
```

After (decontextualized):
```rust
// Pattern: Rate Limiting Middleware
// Works with any HTTP service
pub fn rate_limit<C: RateLimitConfig>(config: &C) -> RateLimiter {
    RateLimiter::new(config.max_requests(), config.window_duration())
}

// Required trait for configuration
pub trait RateLimitConfig {
    fn max_requests(&self) -> u32;
    fn window_duration(&self) -> Duration;
}
```

### Step 2: Document Usage

Every artifact gets documentation following `templates/artifact-card.md`:

**Required sections:**
1. **Title** — descriptive name
2. **When to Use** — conditions where this artifact applies
3. **When NOT to Use** — explicit anti-patterns
4. **Prerequisites** — what must exist before using this
5. **Implementation** — the generalized code/pattern/template
6. **Variants** — alternative implementations for different contexts
7. **Source** — provenance (project, date, version)

**Optional sections:**
- **Gotchas** — things that can go wrong
- **Related Artifacts** — links to complementary artifacts
- **Performance Notes** — benchmarks, trade-offs

### Step 3: Version & Provenance

Every artifact must have a maturity block:

```markdown
## Maturity: 🔴 Alpha
## Used in: [source-project]
## Extracted: [DATE]
## Last updated: [DATE]
## Changelog:
- v1: Initial extraction from [source-project]
```

See `references/maturity-model.md` for maturity progression rules.

## Quality Gate

Apply to each artifact before it can proceed to Phase 4:

| # | Check | Threshold | Blocking? |
|---|-------|-----------|-----------|
| 1 | No project-specific names | 0 remaining | YES |
| 2 | No hardcoded paths | 0 remaining | YES |
| 3 | "When to Use" section | Must exist | YES |
| 4 | "When NOT to Use" section | Must exist | YES |
| 5 | Prerequisites documented | Must exist | YES |
| 6 | At least 1 usage variant | Recommended | NO |
| 7 | Code compiles standalone | Must pass (code) | YES |
| 8 | Maturity level assigned | Must exist | YES |
| 9 | Source project recorded | Must exist | YES |

**If `brutal-honesty-review` skill available:**

Apply Bach-mode BS detection:
- "Is this ACTUALLY reusable, or are we fooling ourselves?"
- "Would this work if transplanted to a completely different project?"
- "Is the generalization genuine or superficial (just renamed variables)?"

## Decontextualization Patterns by Category

### For Patterns
- Replace concrete types with generics/traits/interfaces
- Extract configuration into parameters
- Document the PRINCIPLE, not just the implementation
- Provide at least 2 language/framework variants if possible

### For Commands
- Replace project paths with `$PROJECT_ROOT` or auto-detection
- Make tool dependencies explicit (what must be installed)
- Add argument parsing for project-specific values
- Document required environment variables

### For Rules
- State the UNIVERSAL principle, not the project symptom
- Include example of what goes wrong (without project specifics)
- Specify scope: universal vs. language-specific vs. framework-specific
- Add expiry date for library-specific workarounds

### For Templates
- Replace all hardcoded values with `{{PLACEHOLDERS}}`
- Document every placeholder with type and default value
- Include comments explaining WHY each section exists
- Test that template works with example values

### For Snippets
- Remove all import/require statements that are project-specific
- Document required dependencies
- Add type signatures / function documentation
- Ensure the snippet is self-contained (<50 lines)

### For Skills
- Follow `pipeline-forge` skill anatomy (view `.claude/skills/pipeline-forge/references/skill-anatomy.md`)
- Include SKILL.md with frontmatter
- Add trigger patterns
- Document input/output formats

### For Hooks
- Make the triggering event configurable
- Document which tool/framework the hook targets
- Include installation instructions
- Add enable/disable mechanism

## Output

Each artifact is now a complete, documented, generalized entry ready for toolkit integration.
The output is a set of files (one per artifact) following the `templates/artifact-card.md` format.
