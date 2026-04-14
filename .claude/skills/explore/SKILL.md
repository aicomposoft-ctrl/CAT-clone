---
name: explore
description: >
  Adaptive task exploration and clarification skill for transforming vague 
  requests into actionable specifications. Use when a user presents any task, 
  problem, or goal that requires clarification before execution. Triggers on 
  ambiguous requests, complex multi-part tasks, "I want to...", "help me with...", 
  strategic decisions, product ideas, creative briefs, and any situation where 
  understanding the real need is essential before proposing solutions. Does NOT 
  provide solutions until task is fully explored.
---

# Explore: Adaptive Task Clarification

Transform vague requests into crystal-clear, actionable task specifications through systematic Socratic questioning.

## Core Philosophy

**Never solve before you understand.** Most failed solutions solve the wrong problem. This skill ensures the real problem is understood before any solution is proposed.

Key principles:
- Questions unlock understanding; answers often hide assumptions
- The stated goal is rarely the real goal
- Constraints reveal opportunities
- Success criteria prevent scope creep

## Task Classification

Before asking questions, classify the task type to select appropriate exploration dimensions:

| Task Type | Indicators | Primary Dimensions |
|-----------|------------|-------------------|
| **Product/Feature** | "build", "create app", "develop" | Outcome, Users, Constraints, Success |
| **Problem Solving** | "fix", "solve", "issue with" | Root Cause, Constraints, Attempted Solutions |
| **Decision Making** | "should I", "choose between", "evaluate" | Criteria, Tradeoffs, Timeline, Reversibility |
| **Creative** | "write", "design", "make content" | Audience, Tone, Format, Examples |
| **Research** | "find out", "analyze", "understand" | Scope, Depth, Sources, Deliverable |
| **Process/Workflow** | "how to", "improve process" | Current State, Desired State, Blockers |

## Exploration Dimensions

Select 3-5 dimensions based on task type. Each dimension has multiple question variants—choose the most natural for context.

### 1. The Real Objective
Uncover what success truly looks like, beyond the stated request.

**Questions:**
- "If this worked perfectly, what would be different in your [work/life/business]?"
- "What outcome would make you say 'this was absolutely worth it'?"
- "Is this goal a means to something else, or the end itself?"
- "If you could wave a magic wand and have any result, what would you choose?"

**Red flags to probe:** Generic goals ("make it better"), proxy metrics, solutions presented as requirements.

### 2. Constraints & Boundaries
Identify hard limits that shape the solution space.

**Questions:**
- "What's absolutely off the table—budget, time, technology, or approach-wise?"
- "What existing systems, processes, or decisions must this work with?"
- "Who needs to approve this, and what are their non-negotiables?"
- "What would disqualify a solution, even if it technically works?"

**Red flags to probe:** No constraints mentioned (usually means hidden ones), unrealistic expectations.

### 3. Available Resources
Understand leverage points and existing assets.

**Questions:**
- "What do you already have that we could build on—data, tools, people, prior work?"
- "Who else is involved, and what can they contribute?"
- "What similar problems have you solved before, and what worked?"
- "What's your actual capacity to implement this?"

**Red flags to probe:** Overestimated capabilities, unacknowledged dependencies.

### 4. Timeline & Urgency
Distinguish real deadlines from arbitrary ones.

**Questions:**
- "What happens if this takes 2x longer than expected?"
- "Is there a hard deadline, and what's driving it?"
- "Would you prefer a quick 80% solution or a slower 100% solution?"
- "What's the cost of delay vs. the cost of getting it wrong?"

**Red flags to probe:** Artificial urgency, no clear driver for deadline.

### 5. Success Criteria
Define what "done" actually means.

**Questions:**
- "How will you know this is successful? What will you measure?"
- "Who decides if this is good enough, and what will they look for?"
- "What's the minimum viable outcome that would still be valuable?"
- "In 6 months, what would make you regret the approach we took?"

**Red flags to probe:** Vague criteria ("stakeholders will be happy"), moving targets.

### 6. Attempted Solutions (for problems)
Learn from what hasn't worked.

**Questions:**
- "What have you already tried, and why didn't it work?"
- "What solutions have you considered but rejected?"
- "What would the obvious solution be, and why isn't that good enough?"

### 7. Audience & Stakeholders (for products/content)
Understand who this serves.

**Questions:**
- "Who specifically will use this, and what's their context when they do?"
- "What does your audience already know or believe about this?"
- "Who might be negatively affected, and does that matter?"

## Execution Protocol

### Phase 1: Initial Assessment (1 turn)

1. Parse the user's request
2. Identify what's already clear from context
3. Classify task type
4. Select 3-5 most critical dimensions
5. Note any immediate red flags or assumptions

### Phase 2: Adaptive Questioning (3-7 turns)

**Rules:**
- Ask ONE question at a time
- Make questions specific and decision-shaping, not generic
- Challenge vague answers: "Can you be more specific about...?"
- Acknowledge answers before next question
- Skip dimensions already clarified
- Stop when you have enough to create a clear brief

**Question Sequencing:**
1. Start with Real Objective (reveals the most)
2. Follow with Constraints (narrows solution space)
3. Then Success Criteria (defines done)
4. Fill gaps with other dimensions as needed

**Adaptive behavior:**
- If user gives detailed answer → compress follow-ups
- If user seems frustrated → summarize and ask if they want to continue
- If contradiction detected → gently probe: "Earlier you mentioned X, but now Y—help me understand?"

### Phase 3: Task Brief Synthesis (1 turn)

After sufficient exploration, synthesize into a **Task Brief**:

```
## Task Brief

**Objective:** [Clear statement of what we're actually solving]

**Context:** [Relevant background and constraints]

**Success Criteria:**
- [Measurable criterion 1]
- [Measurable criterion 2]

**Constraints:**
- [Hard constraint 1]
- [Hard constraint 2]

**Resources Available:** [What we can leverage]

**Timeline:** [Deadline and urgency level]

**Key Assumptions:** [Things we're assuming that could change the approach]

**Out of Scope:** [Explicitly excluded items]
```

Ask user: "Does this capture what you need? Anything to add or correct?"

### Phase 4: Handoff

Once validated, either:
- Proceed to solution (if user wants immediate help)
- Export brief for later use
- Suggest appropriate next steps/skills

## Anti-Patterns to Avoid

❌ **Interrogation mode:** Don't fire questions robotically
❌ **Assuming context:** Don't skip clarification because you "think" you understand
❌ **Premature solutions:** Don't hint at solutions before exploration is complete
❌ **Over-questioning:** Stop when you have enough clarity
❌ **Generic questions:** Each question should be tailored to this specific task
❌ **Ignoring signals:** If user provides info proactively, don't re-ask

## Example Flow

**User:** "I want to create a dashboard for my team"

**Claude (Phase 1 assessment):**
- Task type: Product/Feature
- Unclear: Who uses it, what data, what decisions it enables, timeline
- Dimensions needed: Real Objective, Audience, Constraints, Success Criteria

**Claude:** "Before we dive in—what decisions will your team make differently once they have this dashboard? What's the main insight they're missing today?"

*[User answers about tracking project delays]*

**Claude:** "Got it—so the core need is visibility into project health to catch delays early. How do you know a project is delayed today? What's the current process for catching these issues?"

*[Continues adaptively based on answers...]*

## Integration Notes

After exploration, this skill can hand off to:
- problem-solver-enhanced (for complex problems)
- goap-research-ed25519 (for research tasks)
- frontend-design (for UI/product tasks)
- Any implementation skill with the structured Task Brief
