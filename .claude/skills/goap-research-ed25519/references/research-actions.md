# Research Actions Reference (Ed25519 Enhanced)

Complete specifications for GOAP research actions with cryptographic verification extensions.

## Setup Actions (NEW)

### configure_trusted_issuers
**Purpose:** Initialize trusted issuer whitelist for verified research
**Preconditions:** None
**Effects:** `whitelist_active`, `verification_ready`
**Cost:** 0
**Implementation:**
```python
# Load default trusted issuers
verifier = Ed25519Verifier()

# Add custom issuers
verifier.trusted_issuers["custom.org"] = "ed25519:pubkey_base64"

# Set verification threshold
verifier.verification_threshold = 0.95  # strict mode
```
**Success criteria:** Whitelist loaded, verification system initialized

### generate_research_keypair
**Purpose:** Generate Ed25519 keypair for signing research artifacts
**Preconditions:** None
**Effects:** `keypair_available`, `signing_ready`
**Cost:** 1
**Implementation:**
```python
private_key, public_key = verifier.generate_keypair()
# Store securely - never commit private key
```
**Success criteria:** Keypair generated and stored securely

---

## Search Actions

### web_search_broad
**Purpose:** Initial exploration to identify landscape and key subtopics
**Preconditions:** `topic_defined`
**Effects:** `candidates_found`, `subtopics_identified`
**Cost:** 1
**Verification:** None (discovery phase)
**Implementation:**
```
Query strategy:
1. Start with core topic terms
2. Add qualifiers: "overview", "guide", "comprehensive"
3. Note recurring subtopics in results
4. Identify authoritative domains appearing frequently
5. Flag sources from trusted issuers for priority processing
```
**Success criteria:** ≥5 relevant results, ≥3 subtopics identified

### web_search_verified (NEW)
**Purpose:** Search with priority to trusted issuer sources
**Preconditions:** `topic_defined`, `whitelist_active`
**Effects:** `verified_candidates_found`, `trusted_sources_identified`
**Cost:** 2
**Verification:** Domain matching against whitelist
**Implementation:**
```
Query strategy:
1. Include site: operators for trusted domains
   - site:reuters.com OR site:ap.org OR site:nature.com
2. Rank results by issuer trust level
3. Mark trusted vs untrusted sources
4. Prioritize .gov, .edu domains
5. Note signature availability if present
```
**Success criteria:** ≥3 results from trusted issuers

### web_search_specific
**Purpose:** Targeted search for specific information
**Preconditions:** `subtopic_identified` OR `specific_question_formed`
**Effects:** `detail_found`, `sources_identified`
**Cost:** 1
**Verification:** None
**Implementation:**
```
Query strategy:
1. Use exact phrases for specific claims
2. Include domain qualifiers ("site:gov", "site:edu")
3. Add date constraints for temporal queries
4. Use boolean operators for precision
```
**Success criteria:** Direct answers or clear source paths found

### web_search_expert
**Purpose:** Find authoritative voices and expert sources
**Preconditions:** `domain_known`
**Effects:** `authorities_found`, `expert_opinions_available`
**Cost:** 2
**Verification:** Credential verification
**Implementation:**
```
Query patterns:
- "[topic] expert interview"
- "[topic] researcher [institution]"
- "[topic] author [book/paper]"
- "[domain] professor"

Credential verification:
- Check institutional affiliation
- Verify publication history
- Cross-reference expert claims
```
**Success criteria:** ≥2 credentialed experts identified

---

## Content Retrieval Actions

### fetch_source
**Purpose:** Retrieve full content from identified URL
**Preconditions:** `url_known`, `source_accessible`
**Effects:** `content_retrieved`, `full_context_available`
**Cost:** 2
**Verification:** TLS certificate validation
**Implementation:**
- Use web_fetch tool with appropriate URL
- Verify TLS certificate validity
- Handle paywalls by noting limitation
- Extract key sections if full content unavailable
- Note retrieval timestamp
- Calculate content hash for integrity

### fetch_signed_source (NEW)
**Purpose:** Retrieve content with Ed25519 signature verification
**Preconditions:** `url_known`, `issuer_pubkey_available`
**Effects:** `signed_content_retrieved`, `signature_verified`
**Cost:** 3
**Verification:** Ed25519 signature
**Implementation:**
```python
# Fetch content
content = web_fetch(url)

# Check for signature header or metadata
signature = get_signature_from_response(response)
pubkey = get_issuer_pubkey(issuer_domain)

# Verify signature
verified = verifier.verify_signature(content, signature, pubkey)

if verified:
    result.effects.add("signature_verified")
    result.confidence = 0.95
else:
    result.effects.add("signature_invalid")
    result.confidence = 0.5  # Proceed with caution
```
**Success criteria:** Content retrieved, signature verified (if available)

---

## Extraction Actions

### extract_facts
**Purpose:** Systematically extract verifiable claims
**Preconditions:** `content_retrieved`
**Effects:** `facts_cataloged`, `claims_identified`
**Cost:** 1
**Verification:** None (raw extraction)
**Implementation:**
```
Extraction protocol:
1. Identify all factual claims (dates, numbers, names, events)
2. Note source attribution for each fact
3. Flag claims needing verification
4. Record exact quotes with page/section reference
5. Distinguish facts from opinions/interpretations
6. Mark each fact with source_hash for integrity
```

### sign_extracted_facts (NEW)
**Purpose:** Cryptographically sign extracted facts
**Preconditions:** `facts_cataloged`, `keypair_available`
**Effects:** `signed_facts`, `researcher_signature_attached`
**Cost:** 2
**Verification:** Self-signature
**Implementation:**
```python
signed_facts = []
for fact in extracted_facts:
    signed_fact = verifier.create_signed_fact(
        claim=fact.claim,
        source_url=fact.source_url,
        source_content=fact.source_content,
        issuer=researcher_identity
    )
    signed_facts.append(signed_fact)
```
**Output:** List of SignedFact objects with Ed25519 signatures

---

## Verification Actions

### verify_claim
**Purpose:** Confirm or refute specific assertion
**Preconditions:** `claim_identified`, `verification_source_available`
**Effects:** `claim_verified` OR `claim_refuted` OR `claim_uncertain`
**Cost:** 3
**Verification:** Cross-reference (traditional)
**Implementation:**
```
Verification protocol:
1. Locate original/primary source
2. Cross-check with ≥2 independent sources
3. Check for retractions/corrections
4. Verify quoted individuals confirm quotes
5. For statistics: verify methodology, sample, timeframe
```
**Output:** Confidence rating (verified/likely/uncertain/unlikely/refuted)

### verify_claim_cryptographic (NEW)
**Purpose:** Verify claim with cryptographic proof
**Preconditions:** `claim_identified`, `signature_available`, `issuer_pubkey_known`
**Effects:** `cryptographically_verified` OR `signature_invalid`
**Cost:** 4
**Verification:** Ed25519 signature verification
**Implementation:**
```python
def verify_claim_cryptographic(fact: SignedFact) -> VerificationResult:
    # Verify signature
    result = verifier.verify_fact(fact)
    
    if result.verified:
        # Check if issuer is trusted
        if verifier.is_trusted_issuer(fact.issuer):
            result.confidence = 0.95
        else:
            result.confidence = 0.80
    else:
        result.confidence = 0.0
        result.error = "Cryptographic verification failed"
    
    # Log to verification ledger
    verifier.verification_ledger.append(result)
    
    return result
```
**Output:** VerificationResult with confidence score

### cross_reference
**Purpose:** Check consistency across multiple sources
**Preconditions:** `multiple_sources` (≥3)
**Effects:** `consistency_checked`, `contradictions_identified`
**Cost:** 2
**Verification:** None
**Implementation:**
```
Cross-reference matrix:
1. List key claims from each source
2. Mark agreement/disagreement for each claim
3. Note source reliability weighting
4. Identify majority consensus
5. Flag significant contradictions for resolution
```

### cross_reference_signed (NEW)
**Purpose:** Cross-reference with signed source verification
**Preconditions:** `multiple_signed_sources` (≥3)
**Effects:** `signed_consistency_checked`, `multi_source_verified`
**Cost:** 3
**Verification:** Multi-signature verification
**Implementation:**
```python
def cross_reference_signed(facts: List[SignedFact]) -> CrossReferenceResult:
    verified_facts = []
    
    for fact in facts:
        result = verifier.verify_fact(fact)
        if result.verified:
            verified_facts.append(fact)
    
    if len(verified_facts) >= 3:
        # Check claim consistency
        claims = [f.claim for f in verified_facts]
        consistent = check_semantic_consistency(claims)
        
        if consistent:
            return CrossReferenceResult(
                verified=True,
                confidence=min(f.confidence for f in verified_facts) * 1.1,
                sources_count=len(verified_facts)
            )
    
    return CrossReferenceResult(verified=False, confidence=0.0)
```

### find_primary_source
**Purpose:** Trace claim to original source
**Preconditions:** `secondary_source_cites_claim`
**Effects:** `primary_located` OR `primary_unavailable`
**Cost:** 3
**Verification:** None (discovery)
**Implementation:**
```
Tracing protocol:
1. Check footnotes/bibliography of secondary source
2. Search for original publication
3. For statistics: find original study/dataset
4. For quotes: find original interview/speech
5. For events: find contemporaneous reporting
```

---

## Citation Chain Actions (NEW)

### build_citation_chain
**Purpose:** Construct linked chain of cited facts
**Preconditions:** `facts_cataloged`
**Effects:** `citation_chain_complete`
**Cost:** 2
**Verification:** Chain hash integrity
**Implementation:**
```python
def build_citation_chain(facts: List[SignedFact], chain_id: str) -> CitationChain:
    chain = CitationChain(chain_id=chain_id)
    
    for fact in facts:
        chain.add_fact(fact)  # Auto-sets parent_citation
    
    # Calculate chain hash
    chain_hash = chain.get_chain_hash()
    
    return chain
```

### verify_citation_chain
**Purpose:** Verify entire citation chain integrity
**Preconditions:** `citation_chain_complete`
**Effects:** `chain_verified` OR `chain_broken`
**Cost:** 3
**Verification:** Full Ed25519 chain verification
**Implementation:**
```python
def verify_citation_chain(chain: CitationChain) -> Tuple[bool, float]:
    all_verified, aggregate_confidence = verifier.verify_citation_chain(chain)
    
    if all_verified and aggregate_confidence >= verifier.verification_threshold:
        return True, aggregate_confidence
    
    # Identify break point
    for i, fact in enumerate(chain.facts):
        result = verifier.verify_fact(fact)
        if not result.verified:
            return False, 0.0, f"Chain broken at fact {i}: {result.error}"
    
    return all_verified, aggregate_confidence
```

---

## Analysis Actions

### identify_patterns
**Purpose:** Discover recurring themes and connections
**Preconditions:** `facts_cataloged` (≥10 facts)
**Effects:** `patterns_identified`, `themes_emerged`
**Cost:** 2
**Verification:** None
**Implementation:**
- Group related facts
- Identify temporal patterns
- Note causal relationships
- Map entity connections

### timeline_construction
**Purpose:** Establish chronological sequence
**Preconditions:** `events_found` (≥3 dated events)
**Effects:** `chronology_established`, `sequence_clear`
**Cost:** 2
**Verification:** None
**Implementation:**
- Order events by date
- Identify causation vs correlation
- Note gaps in timeline
- Mark uncertain dates

### compare_perspectives
**Purpose:** Document different viewpoints
**Preconditions:** `multiple_perspectives_found`
**Effects:** `viewpoints_mapped`, `disagreements_clarified`
**Cost:** 2
**Verification:** None
**Implementation:**
- Identify distinct positions
- Note supporting evidence for each
- Identify source biases
- Map areas of consensus vs disagreement

---

## Synthesis Actions

### synthesize_findings
**Purpose:** Integrate research into coherent conclusions
**Preconditions:** `facts_verified` (sufficient coverage), `patterns_identified`
**Effects:** `conclusions_formed`, `confidence_assigned`
**Cost:** 3
**Verification:** None (synthesis)
**Implementation:**
```
Synthesis protocol:
1. Review all verified facts
2. Weight by source reliability AND signature status
3. Address contradictions
4. Form conclusions supported by evidence
5. Assign confidence levels (higher for signed sources)
6. Note remaining uncertainties
7. Ensure 100% citation coverage
```

### generate_report
**Purpose:** Produce structured research output
**Preconditions:** `conclusions_formed`
**Effects:** `report_delivered`
**Cost:** 2
**Verification:** None
**Implementation:**
- Follow standard report structure
- Include methodology section
- Cite all sources
- Present confidence assessments
- Document research path

### generate_signed_report (NEW)
**Purpose:** Produce cryptographically signed research report
**Preconditions:** `conclusions_formed`, `keypair_available`
**Effects:** `signed_report_delivered`, `verification_ledger_attached`
**Cost:** 3
**Verification:** Report signature
**Implementation:**
```python
def generate_signed_report(
    findings: ResearchFindings,
    keypair: Keypair
) -> SignedReport:
    # Generate report content
    report = format_report(findings)
    
    # Sign report
    signature, report_hash = verifier.sign_content(report)
    
    # Sign verification ledger
    ledger_sig = verifier.sign_ledger()
    
    return SignedReport(
        content=report,
        signature=signature,
        content_hash=report_hash,
        verification_ledger=verifier.get_verification_ledger(),
        ledger_signature=ledger_sig,
        timestamp=datetime.utcnow().isoformat()
    )
```

---

## Recovery Actions

### expand_search
**Purpose:** Broaden search when stuck
**Preconditions:** `dead_end_reached`
**Effects:** `new_candidates_found` OR `topic_exhausted`
**Cost:** 1
**Verification:** None
**Implementation:**
- Use synonym expansion
- Try related topics
- Search in different languages
- Check academic databases
- Explore adjacent domains
- **Try non-trusted sources with caution**

### pivot_approach
**Purpose:** Change research strategy
**Preconditions:** `current_approach_ineffective`
**Effects:** `new_approach_active`
**Cost:** 1
**Verification:** None
**Implementation:**
- Document why current approach failed
- Identify alternative information paths
- **Consider relaxing verification threshold temporarily**
- Update research plan
- Resume with new strategy

### recover_from_verification_failure (NEW)
**Purpose:** Handle failed signature verification
**Preconditions:** `signature_invalid`
**Effects:** `alternative_source_found` OR `unverified_but_documented`
**Cost:** 2
**Verification:** None
**Implementation:**
```python
def recover_from_verification_failure(fact: SignedFact) -> RecoveryResult:
    # Try to find alternative signed source
    alternatives = search_for_alternatives(fact.claim)
    
    for alt in alternatives:
        if verifier.verify_fact(alt).verified:
            return RecoveryResult(
                success=True,
                alternative_fact=alt
            )
    
    # Document as unverified with lower confidence
    return RecoveryResult(
        success=False,
        original_fact=fact,
        confidence=0.5,
        warning="Claim could not be cryptographically verified"
    )
```

---

## Action Cost Summary

| Action | Base Cost | Verification Overhead | Total |
|--------|-----------|----------------------|-------|
| web_search_broad | 1 | 0 | 1 |
| web_search_verified | 1 | +1 | 2 |
| web_search_specific | 1 | 0 | 1 |
| fetch_source | 2 | 0 | 2 |
| fetch_signed_source | 2 | +1 | 3 |
| extract_facts | 1 | 0 | 1 |
| sign_extracted_facts | 1 | +1 | 2 |
| verify_claim | 3 | 0 | 3 |
| verify_claim_cryptographic | 3 | +1 | 4 |
| cross_reference | 2 | 0 | 2 |
| cross_reference_signed | 2 | +1 | 3 |
| build_citation_chain | 2 | 0 | 2 |
| verify_citation_chain | 2 | +1 | 3 |
| generate_report | 2 | 0 | 2 |
| generate_signed_report | 2 | +1 | 3 |
