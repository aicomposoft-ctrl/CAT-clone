# Source Evaluation Reference (Ed25519 Enhanced)

Comprehensive criteria for assessing source credibility with cryptographic trust layers.

## Trust Model Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TRUST PYRAMID                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    ┌───────────┐                            │
│                    │ Level 6   │ ← Cryptographically        │
│                    │ VERIFIED  │   Signed + Trusted Issuer  │
│                    └─────┬─────┘                            │
│                    ┌─────┴─────┐                            │
│                    │ Level 5   │ ← Primary Sources          │
│                    │ HIGHEST   │   (traditional)            │
│                    └─────┬─────┘                            │
│                ┌─────────┴─────────┐                        │
│                │     Level 4       │ ← Authoritative         │
│                │     HIGH          │   Secondary              │
│                └─────────┬─────────┘                        │
│            ┌─────────────┴─────────────┐                    │
│            │        Level 3            │ ← Reputable         │
│            │        MODERATE           │   General            │
│            └─────────────┬─────────────┘                    │
│        ┌─────────────────┴─────────────────┐                │
│        │           Level 2                 │ ← Community     │
│        │           LOWER                   │                 │
│        └─────────────────┬─────────────────┘                │
│    ┌─────────────────────┴─────────────────────┐            │
│    │              Level 1                      │ ← Unverified│
│    │              MINIMAL                      │             │
│    └───────────────────────────────────────────┘            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Enhanced Reliability Scoring System

### Level 6: Cryptographically Verified (NEW)
**Characteristics:**
- Ed25519 signature verified
- Issuer in trusted whitelist
- Content hash matches signature
- Citation chain intact

**Confidence Score:** 0.95 - 1.00

**Examples:**
- Academic papers with institutional signatures
- Government documents with digital signatures
- Press releases with verified organizational keys
- Official API responses with authentication

**Verification Requirements:**
```python
verified = (
    signature_valid AND
    issuer_in_whitelist AND
    content_hash_matches AND
    timestamp_valid
)
```

**Use for:** Highest-stakes claims, legal evidence, financial data

---

### Level 5: Highest Reliability (Traditional)
**Characteristics:**
- Primary sources (original research, official documents)
- Peer-reviewed academic publications
- Official government/institutional data
- Direct firsthand accounts from verified parties
- Original documentation (contracts, records, footage)

**Confidence Score:** 0.85 - 0.95

**Examples:**
- Published scientific papers in reputable journals
- Government statistical agencies (census, BLS, WHO)
- Official company SEC filings, press releases
- Court documents, legal filings
- Original research datasets

**Use for:** Foundational facts, statistics, direct evidence

---

### Level 4: High Reliability
**Characteristics:**
- Authoritative secondary sources
- Major established publications with editorial oversight
- Recognized domain experts with verifiable credentials
- Well-sourced investigative journalism
- Comprehensive industry reports from established firms

**Confidence Score:** 0.75 - 0.85

**Examples:**
- Major newspapers (NYT, WSJ, Guardian, Reuters, AP)
- Academic review articles
- Industry analysts (Gartner, McKinsey, Forrester)
- Subject matter experts' published work
- Technical documentation from official sources

**Use for:** Analysis, expert interpretation, detailed reporting

---

### Level 3: Moderate Reliability
**Characteristics:**
- Reputable general sources
- Industry publications and trade journals
- Established news websites
- Professional organization publications
- Verified corporate communications

**Confidence Score:** 0.60 - 0.75

**Examples:**
- Industry trade publications
- Regional newspapers
- Professional association reports
- Established tech news sites (Ars Technica, Wired)
- Company blogs (for product information)

**Use for:** Context, industry perspective, supplementary information

---

### Level 2: Lower Reliability
**Characteristics:**
- Community-generated content with some verification
- Personal blogs from demonstrated experts
- User forums with reputation systems
- Self-published but well-researched content
- Secondary aggregation sites

**Confidence Score:** 0.40 - 0.60

**Examples:**
- Stack Overflow (high-reputation answers)
- Medium posts by verified professionals
- Wikipedia (for general context, not citation)
- Specialized forums (verified contributors)
- News aggregators

**Use for:** Starting points, technical troubleshooting, community consensus

---

### Level 1: Minimal Reliability
**Characteristics:**
- Unverified sources
- Anonymous content
- Social media posts
- Content with clear commercial bias
- Rumor or speculation

**Confidence Score:** 0.00 - 0.40

**Examples:**
- Random social media posts
- Anonymous forum comments
- SEO-optimized content farms
- Press releases (for claims about competitors)
- Sponsored content disguised as editorial

**Use for:** Leads only—never cite directly without verification

---

## Cryptographic Trust Multipliers

When Ed25519 verification is available, apply multipliers:

| Verification Status | Multiplier | Effect |
|---------------------|------------|--------|
| Signed + Trusted Issuer | 1.25 | Level 4 → Level 5+ |
| Signed + Unknown Issuer | 1.10 | Slight boost |
| Unsigned | 1.00 | No change |
| Invalid Signature | 0.50 | Major penalty |
| Revoked Key | 0.00 | Reject source |

### Confidence Calculation Formula

```python
def calculate_confidence(source):
    # Base reliability from level
    base = source.level / 5.0  # 0.2 to 1.0
    
    # Verification multiplier
    if source.signature_verified and source.issuer_trusted:
        verification_mult = 1.25
    elif source.signature_verified:
        verification_mult = 1.10
    elif source.signature_invalid:
        verification_mult = 0.50
    else:
        verification_mult = 1.00
    
    # Recency factor
    age_days = (now - source.timestamp).days
    if age_days < 1:
        recency = 1.00
    elif age_days < 7:
        recency = 0.95
    elif age_days < 30:
        recency = 0.85
    elif age_days < 365:
        recency = 0.70
    else:
        recency = 0.50
    
    # Cap at 1.0
    return min(1.0, base * verification_mult * recency)
```

---

## Source Evaluation Checklist (Enhanced)

### Authority Assessment
- [ ] Author/organization identifiable and credentialed
- [ ] Publication has editorial standards
- [ ] Expert credentials relevant to topic
- [ ] Track record of accuracy
- [ ] Institutional backing or peer review
- [ ] **Ed25519 public key registered** (NEW)
- [ ] **Issuer in trusted whitelist** (NEW)

### Cryptographic Assessment (NEW)
- [ ] Content signed with Ed25519
- [ ] Signature verification passes
- [ ] Public key retrievable from trusted source
- [ ] Issuer domain matches claimed origin
- [ ] No key revocation notices
- [ ] Timestamp within acceptable range

### Currency Assessment
- [ ] Publication date clearly stated
- [ ] Information current for topic type
- [ ] No signs of outdated information
- [ ] Updates/corrections noted if applicable
- [ ] **Signature timestamp recent** (NEW)

### Coverage Assessment
- [ ] Scope appropriate to claims made
- [ ] Evidence provided for assertions
- [ ] Methodology explained for research
- [ ] Limitations acknowledged
- [ ] Multiple perspectives considered

### Objectivity Assessment
- [ ] Potential biases identified and manageable
- [ ] Funding/sponsorship disclosed
- [ ] Language neutral (not promotional)
- [ ] Counterarguments addressed
- [ ] Commercial interests declared

### Accuracy Assessment
- [ ] Facts verifiable through other sources
- [ ] Statistics include methodology
- [ ] Quotes attributed and checkable
- [ ] No obvious errors detected
- [ ] Sources cited properly
- [ ] **Content hash matches signature** (NEW)

---

## Trusted Issuer Categories

### Tier 1: Government & Regulatory
**Trust Level:** Highest (auto-Level 5+)
```yaml
tier1_issuers:
  - "*.gov"
  - "*.gov.uk"
  - "*.gov.au"
  - "europa.eu"
  - "who.int"
  - "worldbank.org"
  - "imf.org"
```

### Tier 2: Academic & Research
**Trust Level:** Very High (Level 5)
```yaml
tier2_issuers:
  - "arxiv.org"
  - "nature.com"
  - "science.org"
  - "sciencedirect.com"
  - "springer.com"
  - "ieee.org"
  - "acm.org"
  - "pubmed.gov"
  - "*.edu"
```

### Tier 3: Major News & Wire Services
**Trust Level:** High (Level 4+)
```yaml
tier3_issuers:
  - "reuters.com"
  - "ap.org"
  - "afp.com"
  - "bbc.com"
  - "nytimes.com"
  - "wsj.com"
  - "washingtonpost.com"
  - "economist.com"
  - "ft.com"
```

### Tier 4: Industry & Professional
**Trust Level:** Moderate-High (Level 3-4)
```yaml
tier4_issuers:
  - "gartner.com"
  - "mckinsey.com"
  - "forrester.com"
  - "deloitte.com"
  - "pwc.com"
  - "kpmg.com"
```

---

## Domain-Specific Evaluation (Enhanced)

### Scientific/Medical Information
**Require:** 
- Peer-reviewed sources, established journals
- **Ed25519 signature from institutional key**

**Watch for:** 
- Predatory journals
- Non-replicated studies
- Press releases overstating findings
- **Signatures from unrecognized institutions**

**Verify:** 
- Sample sizes, methodology, conflicts of interest
- Replication status
- **Institutional key registry**

**Minimum Requirements:**
```
Mode: strict (0.95)
Sources: ≥2 Level 5+
Signatures: Required from Tier 2 issuers
```

### Financial/Business Information
**Require:** 
- Official filings, audited statements
- **SEC/regulatory body signatures where applicable**

**Watch for:** 
- Promotional content
- Undisclosed sponsored research
- **Forged corporate signatures**

**Verify:** 
- Numbers against multiple independent sources
- Check for corrections
- **Verify corporate key against official registry**

### Technology Information
**Require:** 
- Official documentation
- Benchmarks with methodology
- **Signed releases from official project keys**

**Watch for:** 
- Marketing claims
- Outdated information (rapid change)
- **Compromised project keys**

**Verify:** 
- Version numbers
- Test conditions
- Community feedback
- **Project key from official source (GitHub, website)**

### Legal Information
**Require:** 
- Primary legal sources
- Licensed attorney commentary
- **Court/government signatures**

**Watch for:** 
- Jurisdiction-specific variations
- Outdated precedents
- **Unofficial legal advice**

**Verify:** 
- Current status of laws/cases
- Jurisdictional applicability
- **Government issuer keys**

### Political/News Information
**Require:** 
- Multiple independent sources
- Primary documentation
- **≥3 Tier 3 issuer signatures**

**Watch for:** 
- Partisan framing
- Selective reporting
- Anonymous sourcing
- **Single-source "scoops" without verification**

**Verify:** 
- Cross-reference across ideologically diverse outlets
- **Multiple independent signatures**

---

## Bias Recognition Matrix (Enhanced)

| Bias Type | Indicators | Mitigation | Verification Help |
|-----------|------------|------------|-------------------|
| Commercial | Promotes product/service, lacks criticism | Seek independent reviews | Require non-commercial issuer |
| Political | One-sided framing, loaded language | Cross-reference opposing viewpoints | Multi-perspective signatures |
| Confirmation | Only supports pre-existing narrative | Actively seek disconfirming evidence | Signed dissenting sources |
| Recency | Overweights recent events | Include historical context | Check timestamp validity |
| Survivorship | Only successful examples shown | Look for failure cases | Academic peer-review sigs |
| Selection | Cherry-picked data/examples | Seek comprehensive datasets | Raw data signatures |
| **Forgery** (NEW) | Claimed sources don't exist | **Verify signatures** | Ed25519 verification |

---

## Verification Requirements by Claim Type (Enhanced)

### Hard Facts (dates, numbers, names)
**Traditional:**
- Minimum: 1 Level 4+ source
- Preferred: Primary source documentation
- Red flag: Only Level 2 or below available

**With Ed25519:**
- Minimum: 1 Level 4+ source OR 1 signed Level 3 source
- Preferred: Signed primary source
- Auto-accept: Level 6 (cryptographically verified)

### Expert Opinions
**Traditional:**
- Minimum: Attributed to named, credentialed expert
- Preferred: Multiple experts agreeing
- Red flag: Anonymous or unverifiable credentials

**With Ed25519:**
- Minimum: Signed by expert's verified key
- Preferred: Institutional countersignature
- Auto-accept: Academic institution signature

### Statistics
**Traditional:**
- Minimum: Methodology disclosed, Level 4+ source
- Preferred: Original study/dataset accessible
- Red flag: No methodology, round numbers without context

**With Ed25519:**
- Minimum: Signed by research institution
- Preferred: Signed raw data + methodology
- Required for strict mode: Institutional signature

### Predictions/Forecasts
- Label confidence explicitly
- Note track record of forecaster
- Present range of expert opinions
- **Never auto-accept signed predictions as facts**

### Controversial Claims
**Traditional:**
- Minimum: 3+ independent Level 3+ sources
- Preferred: Primary evidence available
- Required: Opposing viewpoints documented

**With Ed25519:**
- Minimum: 3+ independently signed sources
- Preferred: Signed primary evidence + 2 corroborations
- Required: Signed opposing viewpoint included

---

## Anti-Hallucination Verification Matrix

| Claim Type | Unsigned OK? | Signature Required? | Strict Mode |
|------------|--------------|---------------------|-------------|
| Historical fact | Yes (Level 4+) | Preferred | Level 5+ |
| Current event | Level 4+ only | Required | Tier 3 sig |
| Scientific claim | Level 5+ only | Required | Tier 2 sig |
| Financial data | No | Required | Regulatory sig |
| Medical advice | No | Required | Institutional sig |
| Legal statement | No | Required | Gov/court sig |
| Expert quote | Level 4+ | Preferred | Expert key |
| Statistics | Level 5+ | Required | Methodology sig |

---

## Source Rejection Criteria

Automatically reject sources with:
- Invalid Ed25519 signature
- Revoked issuer key
- Timestamp >1 year old for current events
- Mismatched content hash
- Unknown issuer in strict mode
- Multiple failed verification attempts
- Blacklisted domain

---

## Confidence Thresholds by Research Mode

| Mode | Threshold | Unsigned Sources | Signature Required |
|------|-----------|------------------|-------------------|
| Development | 0.75 | Allowed (Level 3+) | Optional |
| Moderate | 0.85 | Limited (Level 4+) | Preferred |
| Strict | 0.95 | Rare (Level 5 only) | Required |
| Paranoid | 0.99 | Never | Always (Tier 1-2) |

---

## Appendix: Quick Reference Card

```
┌────────────────────────────────────────────────────────┐
│          SOURCE EVALUATION QUICK REFERENCE             │
├────────────────────────────────────────────────────────┤
│ ALWAYS VERIFY:                                         │
│   ✓ Ed25519 signature (if available)                  │
│   ✓ Issuer against whitelist                          │
│   ✓ Content hash integrity                            │
│   ✓ Timestamp validity                                │
│                                                        │
│ CONFIDENCE FORMULA:                                    │
│   confidence = level/5 × verification × recency        │
│                                                        │
│ MINIMUM REQUIREMENTS:                                  │
│   Facts: 1 signed source OR 2 Level 4+ unsigned       │
│   Stats: Signed methodology OR Level 5+ with method   │
│   Quotes: Signed OR Level 4+ with attribution         │
│                                                        │
│ RED FLAGS:                                             │
│   ✗ Invalid/missing signature in strict mode          │
│   ✗ Unknown issuer for sensitive claims               │
│   ✗ Single source for controversial claims            │
│   ✗ No methodology for statistics                     │
│                                                        │
│ ANTI-HALLUCINATION RULE:                              │
│   "If you can't cite it, don't claim it"              │
└────────────────────────────────────────────────────────┘
```
