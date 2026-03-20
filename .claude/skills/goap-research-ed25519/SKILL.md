---
name: goap-research-ed25519
description: Advanced GOAP research system with Ed25519 cryptographic verification for anti-hallucination protection. Combines Goal-Oriented Action Planning with cryptographic signatures to ensure source authenticity, claim verification, and citation chain integrity. Use for high-stakes research requiring verifiable facts, competitive intelligence, legal/medical research, or any context where hallucination prevention is critical. Triggers on "verified research", "trusted sources only", "anti-hallucination", "signed sources", "cryptographic verification".
---

# GOAP Research Skill with Ed25519 Verification

Advanced research system combining Goal-Oriented Action Planning (GOAP) with Ed25519 cryptographic verification for maximum anti-hallucination protection.

## Key Differentiators from Standard GOAP

| Feature | Standard GOAP | GOAP-Ed25519 |
|---------|---------------|--------------|
| Source Trust | Reliability scoring (1-5) | Cryptographic signatures + scoring |
| Claim Verification | Cross-reference | Cross-reference + signature chain |
| Anti-Hallucination | Triangulation | Triangulation + mandatory citations |
| Audit Trail | Research path log | Signed verification ledger |
| Trust Anchors | Editorial reputation | Trusted issuer whitelist |

## Ed25519 Verification Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    RESEARCH PIPELINE                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Source   │───▶│ Ed25519  │───▶│ Verified │              │
│  │ Content  │    │ Verifier │    │ Facts    │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│        │              │               │                     │
│        ▼              ▼               ▼                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Citation │    │ Signature│    │ Confidence│              │
│  │ Extractor│    │ Chain    │    │ Calculator│              │
│  └──────────┘    └──────────┘    └──────────┘              │
│        │              │               │                     │
│        └──────────────┴───────────────┘                     │
│                       │                                     │
│                       ▼                                     │
│              ┌────────────────┐                             │
│              │ Verification   │                             │
│              │ Ledger (signed)│                             │
│              └────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

## Core GOAP Methodology (Enhanced)

### Phase 1: State Assessment with Trust Initialization

**Define Current State:**
- Existing knowledge about the topic
- Available sources and access constraints
- **NEW:** Trusted issuer whitelist configuration
- **NEW:** Ed25519 keypair availability
- Time and depth requirements

**Define Goal State:**
- Specific questions to answer
- Required evidence types
- **NEW:** Minimum verification threshold (0.85 default, 0.95 strict)
- **NEW:** Required signature chain depth
- Confidence thresholds for conclusions

**Gap Analysis:**
- Knowledge gaps to fill
- **NEW:** Unsigned claims requiring verification
- **NEW:** Citation chain breaks to resolve

### Phase 2: Action Inventory (Extended)

Research actions with Ed25519 verification extensions:

| Action | Preconditions | Effects | Cost | Verification |
|--------|---------------|---------|------|--------------|
| `web_search_broad` | topic_defined | candidates_found | 1 | None |
| `web_search_verified` | topic_defined, trusted_issuers_set | verified_candidates_found | 2 | Domain signature |
| `fetch_source` | url_known | content_retrieved | 2 | TLS certificate |
| `fetch_signed_source` | url_known, issuer_pubkey | signed_content_retrieved | 3 | Ed25519 signature |
| `extract_facts` | content_retrieved | facts_cataloged | 1 | None |
| `sign_extracted_facts` | facts_cataloged, private_key | signed_facts | 2 | Self-signature |
| `verify_claim` | claim_identified | claim_verified/refuted | 3 | Cross-ref |
| `verify_claim_cryptographic` | claim_identified, signature_available | cryptographically_verified | 4 | Ed25519 verify |
| `cross_reference` | multiple_sources | consistency_checked | 2 | None |
| `cross_reference_signed` | multiple_signed_sources | signed_consistency_checked | 3 | Multi-sig verify |
| `build_citation_chain` | facts_cataloged | citation_chain_complete | 2 | Chain integrity |
| `verify_citation_chain` | citation_chain_complete | chain_verified | 3 | Ed25519 chain |
| `generate_signed_report` | conclusions_formed, private_key | signed_report_delivered | 3 | Report signature |

### Phase 3: Plan Generation (A* with Verification Cost)

Enhanced cost function:
```
f(n) = g(n) + h(n) + v(n)
```
- `g(n)`: Actual cost (searches performed, time spent)
- `h(n)`: Heuristic distance to goal (remaining questions)
- `v(n)`: **Verification penalty** (unsigned claims × 0.5)

**Planning Heuristics:**
1. Prioritize signed sources over unsigned (lower total cost)
2. Prefer sources from trusted issuers whitelist
3. Weight cryptographically verified claims higher
4. Factor citation chain depth in confidence

### Phase 4: OODA Loop with Verification Checkpoints

**Observe:**
- Monitor search results quality
- **Track signature validity status**
- **Monitor citation chain integrity**
- Identify information gaps

**Orient:**
- Assess if current path leads to goal
- **Evaluate cryptographic trust level**
- **Check for signature chain breaks**
- Recognize when verification fails

**Decide:**
- Continue current research branch or pivot
- **Accept or reject unsigned sources**
- **Trigger re-verification on suspicious content**
- Choose between depth and breadth

**Act:**
- Execute next optimal action
- **Sign verified findings**
- **Update verification ledger**
- Trigger replanning if deviation detected

### Phase 5: Dynamic Replanning with Trust Recalculation

Trigger replanning when:
- Key assumption invalidated
- **Signature verification fails**
- **Trusted issuer removed from whitelist**
- **Citation chain broken**
- Higher-quality signed source discovered

## Ed25519 Verification Protocol

### Trusted Issuers Whitelist

Default trusted issuers (Level 5 sources):
```yaml
trusted_issuers:
  news:
    - reuters.com
    - ap.org
    - bbc.com
  academic:
    - arxiv.org
    - nature.com
    - science.org
    - pubmed.gov
  government:
    - .gov domains
    - .gov.uk domains
    - europa.eu
  financial:
    - sec.gov
    - federalreserve.gov
    - ecb.europa.eu
```

### Signature Verification Flow

```
1. Source provides content + signature + public_key_id
2. Fetch public key from trusted keyserver or issuer
3. Verify Ed25519 signature: verify(signature, content_hash, public_key)
4. Check issuer against trusted whitelist
5. Record verification result in ledger
6. Assign cryptographic trust score
```

### Citation Chain Verification

Each fact in the chain must have:
```json
{
  "claim": "The statement being made",
  "source_url": "https://...",
  "source_hash": "sha256:abc123...",
  "issuer_pubkey": "ed25519:xyz789...",
  "signature": "ed25519_sig:...",
  "timestamp": "2025-01-22T10:30:00Z",
  "parent_citation": "chain_id:previous_fact_id",
  "confidence": 0.95
}
```

Chain verification:
1. Verify each fact's signature individually
2. Verify chain integrity (parent hashes match)
3. Check all issuers are in trusted whitelist
4. Calculate aggregate chain confidence

## Anti-Hallucination Rules

### 100% Citation Rule
**Every factual claim MUST have a verifiable source.** No exceptions.

```
❌ FORBIDDEN: "Studies show that X leads to Y"
✅ REQUIRED:  "A 2024 study published in Nature (DOI: 10.1038/...) found that X leads to Y"
```

### Verification Thresholds

| Mode | Threshold | Use Case |
|------|-----------|----------|
| `development` | 0.75 | Exploratory research, brainstorming |
| `moderate` | 0.85 | Standard research (default) |
| `strict` | 0.95 | Legal, medical, financial research |
| `paranoid` | 0.99 | Critical decisions, published reports |

### Confidence Calculation

```
confidence = base_reliability × verification_multiplier × recency_factor

where:
  base_reliability = source level (1-5) / 5
  verification_multiplier = 1.0 if unsigned, 1.2 if signed, 1.5 if chain_verified
  recency_factor = 1.0 if <24h, 0.9 if <7d, 0.8 if <30d, 0.6 if older
```

## Research Execution Patterns (Enhanced)

### Pattern A: Verified Exploratory Research
```
Goal: comprehensive_verified_understanding
Actions:
1. configure_trusted_issuers → whitelist_active
2. web_search_verified → verified_candidates_found
3. FOR EACH candidate: fetch_signed_source → signed_content_retrieved
4. extract_facts → facts_cataloged
5. sign_extracted_facts → signed_facts
6. cross_reference_signed → signed_consistency_checked
7. build_citation_chain → citation_chain_complete
8. verify_citation_chain → chain_verified
9. synthesize_findings → conclusions_formed
10. generate_signed_report → signed_report_delivered
```

### Pattern B: High-Stakes Fact Verification
```
Goal: cryptographically_verified_claim
Mode: strict (0.95 threshold)
Actions:
1. identify_claim → claim_defined
2. configure_trusted_issuers (strict list) → whitelist_active
3. find_primary_source → primary_located
4. fetch_signed_source → signed_content_retrieved
5. verify_claim_cryptographic → cryptographically_verified
6. cross_reference_signed (≥3 sources) → multi_source_verified
7. build_citation_chain → citation_chain_complete
8. verify_citation_chain → chain_verified (confidence ≥0.95)
```

### Pattern C: Competitive Analysis with Audit Trail
```
Goal: auditable_competitive_landscape
Actions:
1. identify_players → competitors_listed
2. configure_trusted_issuers → whitelist_active
3. FOR EACH competitor:
   - web_search_verified → verified_info_found
   - fetch_signed_source (official sources) → signed_content
   - extract_facts → facts_cataloged
   - sign_extracted_facts → signed_facts
4. cross_reference_signed → consistency_verified
5. build_citation_chain → full_chain
6. generate_signed_report → auditable_report
```

## Output Structure (Enhanced)

### Verified Research Report Format

```markdown
## Executive Summary
[Key findings in 2-3 sentences]

## Verification Status
- Mode: strict (0.95 threshold)
- Chain Integrity: ✅ VERIFIED
- Unsigned Claims: 0
- Total Citations: 15
- Trusted Issuers Used: 8

## Research Objective
[Original question/goal]

## Methodology
[GOAP plan executed, verification protocol used]

## Verified Findings

### [Subtopic 1]
[Findings with signed inline citations]

**Verification Details:**
| Claim | Source | Signature | Confidence |
|-------|--------|-----------|------------|
| ... | ... | ✅ | 0.96 |

### [Subtopic 2]
[Findings with signed inline citations]

## Confidence Assessment
- Cryptographically Verified (≥0.95): [claims list]
- Cross-Reference Verified (0.85-0.95): [claims list]
- Single Source (0.75-0.85): [claims list]
- Unverified (<0.75): NONE (strict mode)

## Citation Chain
[Full chain with signatures - see Appendix A]

## Verification Ledger
[Signed log of all verification operations]

## Sources
[Numbered list with URLs, signatures, and trust scores]

## Appendix A: Cryptographic Verification Details
[Full Ed25519 signature data for audit]
```

## Quality Standards (Enhanced)

**Completeness Checks:**
- [ ] All original questions addressed
- [ ] **100% of claims have citations**
- [ ] **All citations are verifiable**
- [ ] **Citation chain integrity verified**
- [ ] Primary sources found where possible
- [ ] Contradictions identified and addressed
- [ ] Confidence levels assigned to conclusions
- [ ] **Verification ledger signed and complete**

**Anti-Hallucination Checks:**
- [ ] No claims without sources
- [ ] No "studies show" without specific citation
- [ ] No statistics without methodology source
- [ ] No quotes without attribution + verification
- [ ] No predictions presented as facts

## Implementation

### Python Usage

```python
from goap_planner import GOAPResearchPlanner
from ed25519_verifier import Ed25519Verifier

# Initialize with Ed25519 verification
planner = GOAPResearchPlanner(
    verification_mode="strict",
    trusted_issuers=["reuters.com", "ap.org", "nature.com"]
)

# Generate research plan
plan = planner.plan(
    goal_type="verified_exploratory",
    topic="AI safety regulations 2025"
)

# Execute with verification
results = planner.execute(plan, verify_all=True)

# Generate signed report
report = planner.generate_report(
    results,
    sign=True,
    include_verification_ledger=True
)
```

### CLI Usage (via goalie integration)

```bash
# Install goalie for Ed25519 support
npm install -g goalie

# Verified research
goalie search "Your research question" \
  --verify \
  --strict-verify \
  --trusted-issuers "reuters.com,ap.org,nature.com" \
  --mode academic \
  --save

# Anti-hallucination check
goalie reason --mode anti-hallucination \
  --claims "Your claim to verify" \
  --citations "Source URL"
```

## References

For detailed implementations, see:
- [references/research-actions.md](references/research-actions.md) - Complete action specifications with Ed25519 extensions
- [references/source-evaluation.md](references/source-evaluation.md) - Source credibility with cryptographic trust
- [references/ed25519-verification.md](references/ed25519-verification.md) - Ed25519 protocol details
- [scripts/goap_planner.py](scripts/goap_planner.py) - Enhanced GOAP planner
- [scripts/ed25519_verifier.py](scripts/ed25519_verifier.py) - Verification module

## Dependencies

- Python 3.9+
- `@noble/ed25519` (Node.js) or `cryptography` (Python) for Ed25519
- Optional: `goalie` npm package for CLI integration
