"""Tests for IntegrityChain — HMAC-SHA256 append-only audit trail."""
import pytest
from stochopti.bayesian.integrity import IntegrityChain


def test_chain_append_and_verify():
    key = b"a" * 32  # 256-bit key
    chain = IntegrityChain(key)

    chain.append("INIT", b"state1_digest_placeholder_bytes!")
    chain.append("UPDATE", b"state2_digest_placeholder_bytes!")

    assert chain.get_chain_length() == 2
    assert not chain.compromised
    assert chain.verify_chain() is True


def test_chain_detects_tampering():
    key = b"b" * 32
    chain = IntegrityChain(key)

    chain.append("INIT", b"state1_digest_placeholder_bytes!")
    chain.append("UPDATE", b"state2_digest_placeholder_bytes!")

    # Tamper with an entry's event_type directly
    original = chain._entries[0]
    chain._entries[0] = type(original)(
        seq=original.seq,
        timestamp_utc=original.timestamp_utc,
        event_type="TAMPERED",
        payload_digest=original.payload_digest,
        previous_hash=original.previous_hash,
        entry_hash=original.entry_hash,
    )

    assert chain.verify_chain() is False
    assert chain.compromised


def test_chain_rejects_short_key():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        IntegrityChain(b"short")


def test_sanitize_key():
    key = b"c" * 32
    chain = IntegrityChain(key)
    chain.sanitize_key()
    assert all(b == 0 for b in chain._key)
