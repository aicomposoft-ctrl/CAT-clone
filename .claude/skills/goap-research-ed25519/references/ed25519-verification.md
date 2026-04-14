# Ed25519 Verification Reference

Comprehensive documentation for Ed25519 cryptographic verification in GOAP research.

## Overview

Ed25519 is an elliptic curve digital signature algorithm using Curve25519. It provides:
- **128-bit security level** - resistant to known attacks
- **Fast verification** - ~71,000 verifications/second on modern hardware
- **Small signatures** - 64 bytes
- **Deterministic** - same message + key always produces same signature

## Why Ed25519 for Anti-Hallucination?

| Problem | Ed25519 Solution |
|---------|------------------|
| Source authenticity | Cryptographic proof of origin |
| Content tampering | Hash-based integrity verification |
| Citation chain breaks | Linked signature chains |
| Audit requirements | Signed verification ledger |
| Trust establishment | Trusted issuer whitelist |

## Key Concepts

### Keypair Structure

```
Private Key (Seed): 32 bytes - KEEP SECRET
  └── Used for signing

Public Key: 32 bytes - SHAREABLE
  └── Used for verification
  └── Can be published or fetched from keyserver

Signature: 64 bytes
  └── Proves private key holder signed specific content
```

### Signature Workflow

```
SIGNING (by source/researcher):
  content → SHA-512(content) → Ed25519.sign(hash, private_key) → signature

VERIFICATION (by consumer):
  (content, signature, public_key) → Ed25519.verify() → true/false
```

## Implementation

### Python Implementation

```python
"""
Ed25519 Verification Module for GOAP Research

Requirements:
  pip install cryptography pynacl --break-system-packages
"""

import hashlib
import json
import base64
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field, asdict

# Use cryptography library (preferred) or pynacl
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives import serialization
    CRYPTO_BACKEND = "cryptography"
except ImportError:
    import nacl.signing
    import nacl.encoding
    CRYPTO_BACKEND = "pynacl"


@dataclass
class VerificationResult:
    """Result of a verification operation."""
    verified: bool
    content_hash: str
    signature: str
    issuer: str
    issuer_pubkey: str
    timestamp: str
    confidence: float
    error: Optional[str] = None


@dataclass
class SignedFact:
    """A fact with cryptographic signature."""
    claim: str
    source_url: str
    source_hash: str
    issuer: str
    issuer_pubkey: str
    signature: str
    timestamp: str
    parent_citation: Optional[str] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class CitationChain:
    """Chain of signed citations."""
    chain_id: str
    facts: List[SignedFact] = field(default_factory=list)
    chain_signature: Optional[str] = None
    integrity_verified: bool = False
    
    def add_fact(self, fact: SignedFact) -> None:
        if self.facts:
            fact.parent_citation = f"chain:{self.chain_id}:fact:{len(self.facts)-1}"
        self.facts.append(fact)
    
    def get_chain_hash(self) -> str:
        """Calculate hash of entire chain for signing."""
        chain_data = json.dumps([f.to_dict() for f in self.facts], sort_keys=True)
        return hashlib.sha256(chain_data.encode()).hexdigest()


class Ed25519Verifier:
    """
    Ed25519 verification system for GOAP research.
    
    Provides:
    - Keypair generation
    - Content signing
    - Signature verification
    - Citation chain management
    - Trusted issuer whitelist
    """
    
    DEFAULT_TRUSTED_ISSUERS = {
        # News agencies
        "reuters.com": "ed25519:reuters_pubkey_placeholder",
        "ap.org": "ed25519:ap_pubkey_placeholder",
        "bbc.com": "ed25519:bbc_pubkey_placeholder",
        # Academic
        "arxiv.org": "ed25519:arxiv_pubkey_placeholder",
        "nature.com": "ed25519:nature_pubkey_placeholder",
        "science.org": "ed25519:science_pubkey_placeholder",
        "pubmed.gov": "ed25519:pubmed_pubkey_placeholder",
        # Government
        "sec.gov": "ed25519:sec_pubkey_placeholder",
        "federalreserve.gov": "ed25519:fed_pubkey_placeholder",
    }
    
    def __init__(
        self,
        trusted_issuers: Optional[Dict[str, str]] = None,
        verification_threshold: float = 0.85
    ):
        self.trusted_issuers = trusted_issuers or self.DEFAULT_TRUSTED_ISSUERS
        self.verification_threshold = verification_threshold
        self.verification_ledger: List[VerificationResult] = []
        self._private_key = None
        self._public_key = None
    
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate new Ed25519 keypair."""
        if CRYPTO_BACKEND == "cryptography":
            private_key = Ed25519PrivateKey.generate()
            public_key = private_key.public_key()
            
            private_bytes = private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            )
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
        else:
            signing_key = nacl.signing.SigningKey.generate()
            private_bytes = bytes(signing_key)
            public_bytes = bytes(signing_key.verify_key)
        
        self._private_key = private_bytes
        self._public_key = public_bytes
        
        return private_bytes, public_bytes
    
    def load_keypair(self, private_key: bytes, public_key: bytes) -> None:
        """Load existing keypair."""
        self._private_key = private_key
        self._public_key = public_key
    
    def sign_content(self, content: str) -> Tuple[str, str]:
        """
        Sign content with private key.
        
        Returns:
            Tuple of (signature_base64, content_hash)
        """
        if self._private_key is None:
            raise ValueError("No private key loaded. Call generate_keypair() first.")
        
        content_bytes = content.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        
        if CRYPTO_BACKEND == "cryptography":
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            private_key = Ed25519PrivateKey.from_private_bytes(self._private_key)
            signature = private_key.sign(content_bytes)
        else:
            signing_key = nacl.signing.SigningKey(self._private_key)
            signed = signing_key.sign(content_bytes)
            signature = signed.signature
        
        signature_b64 = base64.b64encode(signature).decode('ascii')
        return signature_b64, content_hash
    
    def verify_signature(
        self,
        content: str,
        signature_b64: str,
        public_key: bytes
    ) -> bool:
        """Verify Ed25519 signature."""
        try:
            content_bytes = content.encode('utf-8')
            signature = base64.b64decode(signature_b64)
            
            if CRYPTO_BACKEND == "cryptography":
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                pub_key = Ed25519PublicKey.from_public_bytes(public_key)
                pub_key.verify(signature, content_bytes)
                return True
            else:
                verify_key = nacl.signing.VerifyKey(public_key)
                verify_key.verify(content_bytes, signature)
                return True
        except Exception:
            return False
    
    def is_trusted_issuer(self, domain: str) -> bool:
        """Check if domain is in trusted issuers whitelist."""
        # Direct match
        if domain in self.trusted_issuers:
            return True
        
        # Suffix match for government domains
        for trusted in self.trusted_issuers:
            if trusted.startswith('.') and domain.endswith(trusted):
                return True
        
        return False
    
    def create_signed_fact(
        self,
        claim: str,
        source_url: str,
        source_content: str,
        issuer: str
    ) -> SignedFact:
        """Create a signed fact with full verification metadata."""
        if self._private_key is None:
            raise ValueError("No private key loaded.")
        
        source_hash = hashlib.sha256(source_content.encode()).hexdigest()
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Sign the claim + source_hash
        signing_content = f"{claim}|{source_hash}|{timestamp}"
        signature, _ = self.sign_content(signing_content)
        
        public_key_b64 = base64.b64encode(self._public_key).decode('ascii')
        
        # Calculate confidence
        base_confidence = 0.8  # Base for signed content
        if self.is_trusted_issuer(issuer):
            base_confidence = 0.95
        
        return SignedFact(
            claim=claim,
            source_url=source_url,
            source_hash=source_hash,
            issuer=issuer,
            issuer_pubkey=f"ed25519:{public_key_b64}",
            signature=signature,
            timestamp=timestamp,
            confidence=base_confidence
        )
    
    def verify_fact(self, fact: SignedFact) -> VerificationResult:
        """Verify a signed fact."""
        # Extract public key from fact
        if not fact.issuer_pubkey.startswith("ed25519:"):
            return VerificationResult(
                verified=False,
                content_hash=fact.source_hash,
                signature=fact.signature,
                issuer=fact.issuer,
                issuer_pubkey=fact.issuer_pubkey,
                timestamp=fact.timestamp,
                confidence=0.0,
                error="Invalid public key format"
            )
        
        try:
            pubkey_b64 = fact.issuer_pubkey[8:]  # Remove "ed25519:" prefix
            public_key = base64.b64decode(pubkey_b64)
            
            # Reconstruct signing content
            signing_content = f"{fact.claim}|{fact.source_hash}|{fact.timestamp}"
            
            verified = self.verify_signature(signing_content, fact.signature, public_key)
            
            # Calculate confidence
            confidence = 0.0
            if verified:
                confidence = 0.8
                if self.is_trusted_issuer(fact.issuer):
                    confidence = 0.95
            
            result = VerificationResult(
                verified=verified,
                content_hash=fact.source_hash,
                signature=fact.signature,
                issuer=fact.issuer,
                issuer_pubkey=fact.issuer_pubkey,
                timestamp=fact.timestamp,
                confidence=confidence,
                error=None if verified else "Signature verification failed"
            )
            
            self.verification_ledger.append(result)
            return result
            
        except Exception as e:
            return VerificationResult(
                verified=False,
                content_hash=fact.source_hash,
                signature=fact.signature,
                issuer=fact.issuer,
                issuer_pubkey=fact.issuer_pubkey,
                timestamp=fact.timestamp,
                confidence=0.0,
                error=str(e)
            )
    
    def verify_citation_chain(self, chain: CitationChain) -> Tuple[bool, float]:
        """
        Verify entire citation chain integrity.
        
        Returns:
            Tuple of (all_verified, aggregate_confidence)
        """
        if not chain.facts:
            return False, 0.0
        
        all_verified = True
        total_confidence = 0.0
        
        for i, fact in enumerate(chain.facts):
            result = self.verify_fact(fact)
            
            if not result.verified:
                all_verified = False
            
            total_confidence += result.confidence
            
            # Verify chain linkage
            if i > 0:
                expected_parent = f"chain:{chain.chain_id}:fact:{i-1}"
                if fact.parent_citation != expected_parent:
                    all_verified = False
        
        aggregate_confidence = total_confidence / len(chain.facts)
        chain.integrity_verified = all_verified
        
        return all_verified, aggregate_confidence
    
    def get_verification_ledger(self) -> List[Dict]:
        """Get verification ledger as list of dicts."""
        return [asdict(r) for r in self.verification_ledger]
    
    def sign_ledger(self) -> str:
        """Sign the entire verification ledger."""
        ledger_json = json.dumps(self.get_verification_ledger(), sort_keys=True)
        signature, _ = self.sign_content(ledger_json)
        return signature


# Convenience functions for standalone usage
def generate_keypair() -> Tuple[str, str]:
    """Generate keypair and return as base64 strings."""
    verifier = Ed25519Verifier()
    private_bytes, public_bytes = verifier.generate_keypair()
    return (
        base64.b64encode(private_bytes).decode('ascii'),
        base64.b64encode(public_bytes).decode('ascii')
    )


def sign_content(content: str, private_key_b64: str) -> str:
    """Sign content with base64-encoded private key."""
    verifier = Ed25519Verifier()
    private_bytes = base64.b64decode(private_key_b64)
    # Derive public key from private (first 32 bytes are seed)
    if CRYPTO_BACKEND == "cryptography":
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        pk = Ed25519PrivateKey.from_private_bytes(private_bytes)
        pub_bytes = pk.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
    else:
        signing_key = nacl.signing.SigningKey(private_bytes)
        pub_bytes = bytes(signing_key.verify_key)
    
    verifier.load_keypair(private_bytes, pub_bytes)
    signature, _ = verifier.sign_content(content)
    return signature


def verify_content(content: str, signature_b64: str, public_key_b64: str) -> bool:
    """Verify content signature with base64-encoded public key."""
    verifier = Ed25519Verifier()
    public_bytes = base64.b64decode(public_key_b64)
    return verifier.verify_signature(content, signature_b64, public_bytes)
```

### Node.js Implementation

```javascript
/**
 * Ed25519 Verification Module for GOAP Research
 * 
 * Requirements:
 *   npm install @noble/ed25519
 */

import * as ed from '@noble/ed25519';
import { sha512 } from '@noble/hashes/sha512';
import { createHash } from 'crypto';

// Enable sync methods
ed.etc.sha512Sync = (...m) => sha512(ed.etc.concatBytes(...m));

/**
 * Generate Ed25519 keypair
 * @returns {Promise<{privateKey: Uint8Array, publicKey: Uint8Array}>}
 */
async function generateKeypair() {
  const privateKey = ed.utils.randomPrivateKey();
  const publicKey = await ed.getPublicKeyAsync(privateKey);
  return { privateKey, publicKey };
}

/**
 * Sign content
 * @param {string} content - Content to sign
 * @param {Uint8Array} privateKey - Private key
 * @returns {Promise<{signature: string, contentHash: string}>}
 */
async function signContent(content, privateKey) {
  const contentBytes = new TextEncoder().encode(content);
  const contentHash = createHash('sha256').update(contentBytes).digest('hex');
  const signature = await ed.signAsync(contentBytes, privateKey);
  return {
    signature: Buffer.from(signature).toString('base64'),
    contentHash
  };
}

/**
 * Verify signature
 * @param {string} content - Original content
 * @param {string} signatureB64 - Base64 signature
 * @param {Uint8Array} publicKey - Public key
 * @returns {Promise<boolean>}
 */
async function verifySignature(content, signatureB64, publicKey) {
  try {
    const contentBytes = new TextEncoder().encode(content);
    const signature = Buffer.from(signatureB64, 'base64');
    return await ed.verifyAsync(signature, contentBytes, publicKey);
  } catch {
    return false;
  }
}

/**
 * Create signed fact
 */
async function createSignedFact(claim, sourceUrl, sourceContent, issuer, privateKey, publicKey) {
  const sourceHash = createHash('sha256')
    .update(sourceContent)
    .digest('hex');
  
  const timestamp = new Date().toISOString();
  const signingContent = `${claim}|${sourceHash}|${timestamp}`;
  const { signature } = await signContent(signingContent, privateKey);
  
  return {
    claim,
    source_url: sourceUrl,
    source_hash: sourceHash,
    issuer,
    issuer_pubkey: `ed25519:${Buffer.from(publicKey).toString('base64')}`,
    signature,
    timestamp,
    parent_citation: null,
    confidence: 0.8
  };
}

/**
 * Verify signed fact
 */
async function verifyFact(fact) {
  const pubkeyB64 = fact.issuer_pubkey.replace('ed25519:', '');
  const publicKey = Buffer.from(pubkeyB64, 'base64');
  
  const signingContent = `${fact.claim}|${fact.source_hash}|${fact.timestamp}`;
  const verified = await verifySignature(signingContent, fact.signature, publicKey);
  
  return {
    verified,
    content_hash: fact.source_hash,
    signature: fact.signature,
    issuer: fact.issuer,
    timestamp: fact.timestamp,
    confidence: verified ? 0.8 : 0.0,
    error: verified ? null : 'Signature verification failed'
  };
}

export {
  generateKeypair,
  signContent,
  verifySignature,
  createSignedFact,
  verifyFact
};
```

## Trusted Issuer Management

### Adding Custom Trusted Issuers

```python
verifier = Ed25519Verifier()

# Add organization's public key
verifier.trusted_issuers["mycompany.com"] = "ed25519:base64_encoded_pubkey"

# Add academic institution
verifier.trusted_issuers["mit.edu"] = "ed25519:mit_pubkey"
```

### Fetching Public Keys

In production, public keys should be fetched from:
1. **DNS TXT records** - `_ed25519.domain.com`
2. **Well-known endpoints** - `/.well-known/ed25519-keys.json`
3. **Keyservers** - Similar to PGP keyservers

Example DNS lookup:
```bash
dig TXT _ed25519.reuters.com
```

## Security Considerations

### Key Management
- **Never commit private keys** to repositories
- Use environment variables or secure vaults
- Rotate keys periodically
- Maintain key revocation lists

### Verification Limitations
- Ed25519 proves who signed, not truthfulness
- Trust still depends on issuer integrity
- Signatures don't prevent plagiarism
- Timestamps can be backdated by signer

### Attack Vectors
| Attack | Mitigation |
|--------|------------|
| Key compromise | Regular rotation, revocation checks |
| Replay attacks | Include timestamps, nonces |
| Man-in-the-middle | TLS + signature verification |
| Fake issuers | Strict whitelist management |

## Integration with GOAP Actions

### New Actions Added

| Action | Input | Output | Verification |
|--------|-------|--------|--------------|
| `configure_trusted_issuers` | issuer list | whitelist_active | None |
| `fetch_signed_source` | URL + pubkey | signed_content | Ed25519 |
| `sign_extracted_facts` | facts + privkey | signed_facts | Self-sig |
| `verify_claim_cryptographic` | claim + sig | verified | Ed25519 |
| `build_citation_chain` | facts | chain | Chain hash |
| `verify_citation_chain` | chain | verified_chain | Chain sigs |
| `generate_signed_report` | report + privkey | signed_report | Ed25519 |

### Cost Adjustments

Verification adds overhead:
- `fetch_signed_source`: +1 cost (verification time)
- `verify_claim_cryptographic`: +1 cost
- `verify_citation_chain`: +2 cost (full chain traversal)

But provides verification bonus in confidence calculation.

## CLI Reference

### Using with goalie

```bash
# Verified search
goalie search "query" --verify --strict-verify

# Check issuer trust
goalie trust check "reuters.com"

# Add trusted issuer
goalie trust add "mycompany.com" --pubkey "ed25519:..."

# Verify existing fact
goalie verify --fact '{"claim":"...", "signature":"..."}'

# Generate research keypair
goalie keys generate --output ./research-keys.json
```

## Appendix: Test Vectors

### Test Keypair
```
Private (seed): 9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60
Public:         d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a
```

### Test Signature
```
Message: "Test message for GOAP research"
Signature: e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b
```

Verify: `Ed25519.verify(signature, message, public_key) == true`
