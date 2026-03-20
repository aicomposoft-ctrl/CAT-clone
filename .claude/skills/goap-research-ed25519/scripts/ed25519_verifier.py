#!/usr/bin/env python3
"""
Ed25519 Verification Module for GOAP Research

Provides cryptographic verification capabilities for research workflows:
- Keypair generation
- Content signing
- Signature verification  
- Citation chain management
- Trusted issuer whitelist
- Verification ledger

Requirements:
    pip install cryptography --break-system-packages
    # OR
    pip install pynacl --break-system-packages
"""

import hashlib
import json
import base64
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field, asdict
import os

# Try to import cryptography library (preferred)
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    CRYPTO_BACKEND = "cryptography"
except ImportError:
    try:
        import nacl.signing
        import nacl.encoding
        import nacl.exceptions
        CRYPTO_BACKEND = "pynacl"
    except ImportError:
        CRYPTO_BACKEND = None


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
    
    def to_dict(self) -> Dict:
        return asdict(self)


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
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SignedFact':
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SignedFact':
        return cls.from_dict(json.loads(json_str))


@dataclass
class CitationChain:
    """Chain of signed citations with integrity verification."""
    chain_id: str
    facts: List[SignedFact] = field(default_factory=list)
    chain_signature: Optional[str] = None
    chain_hash: Optional[str] = None
    integrity_verified: bool = False
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_fact(self, fact: SignedFact) -> None:
        """Add fact to chain with automatic parent linking."""
        if self.facts:
            fact.parent_citation = f"chain:{self.chain_id}:fact:{len(self.facts)-1}"
        self.facts.append(fact)
        self.chain_hash = None  # Invalidate cached hash
    
    def get_chain_hash(self) -> str:
        """Calculate hash of entire chain for signing."""
        if self.chain_hash is None:
            chain_data = json.dumps(
                [f.to_dict() for f in self.facts], 
                sort_keys=True
            )
            self.chain_hash = hashlib.sha256(chain_data.encode()).hexdigest()
        return self.chain_hash
    
    def to_dict(self) -> Dict:
        return {
            'chain_id': self.chain_id,
            'facts': [f.to_dict() for f in self.facts],
            'chain_signature': self.chain_signature,
            'chain_hash': self.get_chain_hash(),
            'integrity_verified': self.integrity_verified,
            'created_at': self.created_at
        }


class Ed25519Verifier:
    """
    Ed25519 verification system for GOAP research.
    
    Provides:
    - Keypair generation and management
    - Content signing and verification
    - Citation chain management
    - Trusted issuer whitelist
    - Verification ledger
    """
    
    DEFAULT_TRUSTED_ISSUERS = {
        # News agencies
        "reuters.com": None,
        "ap.org": None,
        "bbc.com": None,
        "nytimes.com": None,
        "wsj.com": None,
        # Academic
        "arxiv.org": None,
        "nature.com": None,
        "science.org": None,
        "sciencedirect.com": None,
        "pubmed.gov": None,
        "ieee.org": None,
        "acm.org": None,
        # Government
        ".gov": None,  # Suffix match
        ".gov.uk": None,
        "europa.eu": None,
        "who.int": None,
        # Financial/Regulatory
        "sec.gov": None,
        "federalreserve.gov": None,
        "ecb.europa.eu": None,
    }
    
    def __init__(
        self,
        trusted_issuers: Optional[Dict[str, Optional[str]]] = None,
        verification_threshold: float = 0.85,
        auto_generate_keypair: bool = False
    ):
        """
        Initialize verifier.
        
        Args:
            trusted_issuers: Dict of domain -> public_key_b64 (None = trust without signature)
            verification_threshold: Minimum confidence for verified status
            auto_generate_keypair: Generate keypair on init
        """
        if CRYPTO_BACKEND is None:
            raise RuntimeError(
                "No cryptographic backend available. Install cryptography or pynacl:\n"
                "  pip install cryptography --break-system-packages"
            )
        
        self.trusted_issuers = trusted_issuers or self.DEFAULT_TRUSTED_ISSUERS.copy()
        self.verification_threshold = verification_threshold
        self.verification_ledger: List[VerificationResult] = []
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None
        
        if auto_generate_keypair:
            self.generate_keypair()
    
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """
        Generate new Ed25519 keypair.
        
        Returns:
            Tuple of (private_key_bytes, public_key_bytes)
        """
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
        else:  # pynacl
            signing_key = nacl.signing.SigningKey.generate()
            private_bytes = bytes(signing_key)
            public_bytes = bytes(signing_key.verify_key)
        
        self._private_key = private_bytes
        self._public_key = public_bytes
        
        return private_bytes, public_bytes
    
    def load_keypair(self, private_key: bytes, public_key: Optional[bytes] = None) -> None:
        """
        Load existing keypair.
        
        Args:
            private_key: 32-byte private key (seed)
            public_key: 32-byte public key (optional, can be derived)
        """
        self._private_key = private_key
        
        if public_key is not None:
            self._public_key = public_key
        else:
            # Derive public key from private
            if CRYPTO_BACKEND == "cryptography":
                pk = Ed25519PrivateKey.from_private_bytes(private_key)
                self._public_key = pk.public_key().public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
            else:
                signing_key = nacl.signing.SigningKey(private_key)
                self._public_key = bytes(signing_key.verify_key)
    
    def load_keypair_from_files(self, private_path: str, public_path: Optional[str] = None) -> None:
        """Load keypair from files."""
        with open(private_path, 'rb') as f:
            private_key = f.read()
        
        public_key = None
        if public_path:
            with open(public_path, 'rb') as f:
                public_key = f.read()
        
        self.load_keypair(private_key, public_key)
    
    def save_keypair_to_files(self, private_path: str, public_path: str) -> None:
        """Save keypair to files."""
        if self._private_key is None or self._public_key is None:
            raise ValueError("No keypair to save. Generate or load one first.")
        
        with open(private_path, 'wb') as f:
            f.write(self._private_key)
        os.chmod(private_path, 0o600)  # Restrict private key permissions
        
        with open(public_path, 'wb') as f:
            f.write(self._public_key)
    
    def get_public_key_b64(self) -> str:
        """Get public key as base64 string."""
        if self._public_key is None:
            raise ValueError("No public key available.")
        return base64.b64encode(self._public_key).decode('ascii')
    
    def sign_content(self, content: str) -> Tuple[str, str]:
        """
        Sign content with private key.
        
        Args:
            content: String content to sign
        
        Returns:
            Tuple of (signature_base64, content_sha256_hash)
        """
        if self._private_key is None:
            raise ValueError("No private key loaded. Call generate_keypair() first.")
        
        content_bytes = content.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        
        if CRYPTO_BACKEND == "cryptography":
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
        """
        Verify Ed25519 signature.
        
        Args:
            content: Original content
            signature_b64: Base64-encoded signature
            public_key: 32-byte public key
        
        Returns:
            True if valid, False otherwise
        """
        try:
            content_bytes = content.encode('utf-8')
            signature = base64.b64decode(signature_b64)
            
            if CRYPTO_BACKEND == "cryptography":
                pub_key = Ed25519PublicKey.from_public_bytes(public_key)
                pub_key.verify(signature, content_bytes)
                return True
            else:
                verify_key = nacl.signing.VerifyKey(public_key)
                verify_key.verify(content_bytes, signature)
                return True
        except (InvalidSignature, nacl.exceptions.BadSignatureError) if CRYPTO_BACKEND == "pynacl" else InvalidSignature:
            return False
        except Exception:
            return False
    
    def is_trusted_issuer(self, domain: str) -> bool:
        """Check if domain is in trusted issuers whitelist."""
        # Direct match
        if domain in self.trusted_issuers:
            return True
        
        # Suffix match for patterns like ".gov"
        for trusted in self.trusted_issuers:
            if trusted.startswith('.') and domain.endswith(trusted):
                return True
        
        # Check if any trusted issuer is a suffix of the domain
        for trusted in self.trusted_issuers:
            if domain.endswith('.' + trusted) or domain == trusted:
                return True
        
        return False
    
    def add_trusted_issuer(self, domain: str, public_key_b64: Optional[str] = None) -> None:
        """Add domain to trusted issuers."""
        self.trusted_issuers[domain] = public_key_b64
    
    def remove_trusted_issuer(self, domain: str) -> None:
        """Remove domain from trusted issuers."""
        self.trusted_issuers.pop(domain, None)
    
    def create_signed_fact(
        self,
        claim: str,
        source_url: str,
        source_content: str,
        issuer: str,
        metadata: Optional[Dict] = None
    ) -> SignedFact:
        """
        Create a signed fact with full verification metadata.
        
        Args:
            claim: The factual claim being made
            source_url: URL of the source
            source_content: Content from the source
            issuer: Domain/identity of the issuer
            metadata: Additional metadata
        
        Returns:
            SignedFact with Ed25519 signature
        """
        if self._private_key is None:
            raise ValueError("No private key loaded.")
        
        source_hash = hashlib.sha256(source_content.encode()).hexdigest()
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Sign the claim + source_hash + timestamp
        signing_content = f"{claim}|{source_hash}|{timestamp}"
        signature, _ = self.sign_content(signing_content)
        
        public_key_b64 = base64.b64encode(self._public_key).decode('ascii')
        
        # Calculate confidence
        base_confidence = 0.80  # Base for signed content
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
            confidence=base_confidence,
            metadata=metadata or {}
        )
    
    def verify_fact(self, fact: SignedFact) -> VerificationResult:
        """
        Verify a signed fact.
        
        Args:
            fact: SignedFact to verify
        
        Returns:
            VerificationResult with status and confidence
        """
        # Extract public key from fact
        if not fact.issuer_pubkey.startswith("ed25519:"):
            result = VerificationResult(
                verified=False,
                content_hash=fact.source_hash,
                signature=fact.signature,
                issuer=fact.issuer,
                issuer_pubkey=fact.issuer_pubkey,
                timestamp=fact.timestamp,
                confidence=0.0,
                error="Invalid public key format (expected 'ed25519:...')"
            )
            self.verification_ledger.append(result)
            return result
        
        try:
            pubkey_b64 = fact.issuer_pubkey[8:]  # Remove "ed25519:" prefix
            public_key = base64.b64decode(pubkey_b64)
            
            # Reconstruct signing content
            signing_content = f"{fact.claim}|{fact.source_hash}|{fact.timestamp}"
            
            verified = self.verify_signature(signing_content, fact.signature, public_key)
            
            # Calculate confidence
            confidence = 0.0
            if verified:
                confidence = 0.80
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
            result = VerificationResult(
                verified=False,
                content_hash=fact.source_hash,
                signature=fact.signature,
                issuer=fact.issuer,
                issuer_pubkey=fact.issuer_pubkey,
                timestamp=fact.timestamp,
                confidence=0.0,
                error=str(e)
            )
            self.verification_ledger.append(result)
            return result
    
    def verify_citation_chain(self, chain: CitationChain) -> Tuple[bool, float, Optional[str]]:
        """
        Verify entire citation chain integrity.
        
        Args:
            chain: CitationChain to verify
        
        Returns:
            Tuple of (all_verified, aggregate_confidence, error_message)
        """
        if not chain.facts:
            return False, 0.0, "Empty chain"
        
        all_verified = True
        total_confidence = 0.0
        errors = []
        
        for i, fact in enumerate(chain.facts):
            result = self.verify_fact(fact)
            
            if not result.verified:
                all_verified = False
                errors.append(f"Fact {i}: {result.error}")
            
            total_confidence += result.confidence
            
            # Verify chain linkage
            if i > 0:
                expected_parent = f"chain:{chain.chain_id}:fact:{i-1}"
                if fact.parent_citation != expected_parent:
                    all_verified = False
                    errors.append(f"Fact {i}: Invalid parent citation")
        
        aggregate_confidence = total_confidence / len(chain.facts)
        chain.integrity_verified = all_verified
        
        error_msg = "; ".join(errors) if errors else None
        return all_verified, aggregate_confidence, error_msg
    
    def sign_chain(self, chain: CitationChain) -> str:
        """Sign the entire citation chain."""
        chain_hash = chain.get_chain_hash()
        signature, _ = self.sign_content(chain_hash)
        chain.chain_signature = signature
        return signature
    
    def get_verification_ledger(self) -> List[Dict]:
        """Get verification ledger as list of dicts."""
        return [r.to_dict() for r in self.verification_ledger]
    
    def sign_ledger(self) -> str:
        """Sign the entire verification ledger."""
        ledger_json = json.dumps(self.get_verification_ledger(), sort_keys=True)
        signature, _ = self.sign_content(ledger_json)
        return signature
    
    def export_ledger(self, filepath: str) -> None:
        """Export verification ledger to file."""
        data = {
            'ledger': self.get_verification_ledger(),
            'signature': self.sign_ledger(),
            'exported_at': datetime.utcnow().isoformat() + "Z",
            'signer_pubkey': f"ed25519:{self.get_public_key_b64()}" if self._public_key else None
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def clear_ledger(self) -> None:
        """Clear the verification ledger."""
        self.verification_ledger.clear()


# Convenience functions
def generate_keypair_b64() -> Tuple[str, str]:
    """Generate keypair and return as base64 strings."""
    verifier = Ed25519Verifier()
    private_bytes, public_bytes = verifier.generate_keypair()
    return (
        base64.b64encode(private_bytes).decode('ascii'),
        base64.b64encode(public_bytes).decode('ascii')
    )


def quick_sign(content: str, private_key_b64: str) -> str:
    """Quick sign content with base64-encoded private key."""
    verifier = Ed25519Verifier()
    private_bytes = base64.b64decode(private_key_b64)
    verifier.load_keypair(private_bytes)
    signature, _ = verifier.sign_content(content)
    return signature


def quick_verify(content: str, signature_b64: str, public_key_b64: str) -> bool:
    """Quick verify content signature."""
    verifier = Ed25519Verifier()
    public_bytes = base64.b64decode(public_key_b64)
    return verifier.verify_signature(content, signature_b64, public_bytes)


# Demo and testing
if __name__ == "__main__":
    print("Ed25519 Verification Module Demo")
    print("=" * 60)
    print(f"Crypto Backend: {CRYPTO_BACKEND}")
    print()
    
    # Initialize verifier
    verifier = Ed25519Verifier(
        verification_threshold=0.85,
        auto_generate_keypair=True
    )
    
    print(f"Public Key: ed25519:{verifier.get_public_key_b64()[:32]}...")
    print()
    
    # Create and sign a fact
    print("[1] Creating signed fact...")
    fact = verifier.create_signed_fact(
        claim="The study found a 25% improvement in efficiency",
        source_url="https://nature.com/articles/example",
        source_content="Full article content here...",
        issuer="nature.com"
    )
    
    print(f"Claim: {fact.claim}")
    print(f"Source: {fact.source_url}")
    print(f"Signature: {fact.signature[:32]}...")
    print(f"Confidence: {fact.confidence}")
    print()
    
    # Verify the fact
    print("[2] Verifying signed fact...")
    result = verifier.verify_fact(fact)
    print(f"Verified: {result.verified}")
    print(f"Confidence: {result.confidence}")
    print(f"Error: {result.error}")
    print()
    
    # Create citation chain
    print("[3] Building citation chain...")
    chain = CitationChain(chain_id="research_001")
    
    for i in range(3):
        fact = verifier.create_signed_fact(
            claim=f"Claim {i+1} from the research",
            source_url=f"https://source{i+1}.com/article",
            source_content=f"Source content {i+1}",
            issuer=["reuters.com", "arxiv.org", "example.com"][i]
        )
        chain.add_fact(fact)
    
    print(f"Chain ID: {chain.chain_id}")
    print(f"Facts: {len(chain.facts)}")
    print(f"Chain Hash: {chain.get_chain_hash()[:32]}...")
    print()
    
    # Verify chain
    print("[4] Verifying citation chain...")
    all_verified, confidence, error = verifier.verify_citation_chain(chain)
    print(f"All Verified: {all_verified}")
    print(f"Aggregate Confidence: {confidence:.2%}")
    print(f"Errors: {error}")
    print()
    
    # Sign chain
    chain_sig = verifier.sign_chain(chain)
    print(f"Chain Signature: {chain_sig[:32]}...")
    print()
    
    # Verification ledger
    print("[5] Verification Ledger:")
    for i, entry in enumerate(verifier.get_verification_ledger()):
        print(f"  {i+1}. {entry['issuer']}: {'✅' if entry['verified'] else '❌'} "
              f"(confidence: {entry['confidence']:.2%})")
    
    print()
    print("=" * 60)
    print("Demo complete!")
