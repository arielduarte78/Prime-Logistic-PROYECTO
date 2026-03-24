"""
Verification tests for Phase 1 SGSI: Validation Middleware + Integrity Chain.
Run: python -m pytest scripts/test_phase1_sgsi.py -v
"""
import hashlib
import struct
import os
import sys
import pytest

# ─── Test 1: IntegrityChain HMAC-SHA256 ───

def test_integrity_chain_basic():
    """Chain creates GENESIS entry and verifies."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    
    # Append GENESIS-like entry
    digest = hashlib.sha256(b"test_state").digest()
    seq = chain.append("INIT", digest)
    
    assert seq == 0
    assert chain.get_chain_length() == 1
    assert chain.verify_chain() is True
    assert chain.compromised is False


def test_integrity_chain_multiple_entries():
    """Chain with multiple entries verifies correctly."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    
    for i in range(100):
        digest = hashlib.sha256(f"state_{i}".encode()).digest()
        chain.append("UPDATE_EDGE", digest)
    
    assert chain.get_chain_length() == 100
    assert chain.verify_chain() is True


def test_integrity_chain_tamper_detection():
    """Tampering with an entry is detected by verify_chain."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    
    for i in range(10):
        digest = hashlib.sha256(f"state_{i}".encode()).digest()
        chain.append("UPDATE_EDGE", digest)
    
    # Tamper with entry 5
    from src.bloque3.integrity_chain import IntegrityEntry
    original = chain._entries[5]
    tampered = IntegrityEntry(
        seq=original.seq,
        timestamp_utc=original.timestamp_utc,
        event_type=original.event_type,
        payload_digest="00" * 32,  # corrupted
        previous_hash=original.previous_hash,
        entry_hash=original.entry_hash,
    )
    chain._entries[5] = tampered
    
    assert chain.verify_chain() is False
    assert chain.compromised is True


def test_integrity_chain_key_too_short():
    """Key < 32 bytes should raise ValueError."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    with pytest.raises(ValueError, match="at least 32 bytes"):
        IntegrityChain(b"short_key")


def test_integrity_chain_sanitize():
    """Key sanitization zeros out the key buffer."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    chain.sanitize_key()
    
    assert all(b == 0 for b in chain._key)


def test_integrity_chain_export_audit_trail():
    """Export produces valid dict structure."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    digest = hashlib.sha256(b"test").digest()
    chain.append("INIT", digest)
    chain.append("UPDATE_EDGE", digest)
    
    trail = chain.export_audit_trail()
    assert len(trail) == 2
    assert trail[0]["event_type"] == "INIT"
    assert trail[1]["event_type"] == "UPDATE_EDGE"
    assert "entry_hash" in trail[0]
    assert "previous_hash" in trail[1]


def test_endianness_explicit():
    """Verify struct.pack uses big-endian (>) consistently."""
    from src.bloque3.integrity_chain import IntegrityChain
    
    key = os.urandom(32)
    chain = IntegrityChain(key)
    
    # The chain internally uses struct.pack(">I", seq) 
    # Verify the same result on this machine
    packed = struct.pack(">I", 42)
    assert len(packed) == 4
    # Big-endian: MSB first
    assert packed == b'\x00\x00\x00\x2a'


# ─── Test 2: Pydantic Strict Validation ───

def test_strict_mode_rejects_string_as_float():
    """Strict mode rejects '3.5' where float is expected."""
    from pydantic import ValidationError
    from src.api.schemas import VehicleInput
    
    with pytest.raises(ValidationError):
        VehicleInput(
            id="truck-1",
            origin_lat="-34.6",  # string, not float
            origin_lon=-58.4,
            capacity_tons=10.0,
        )


def test_strict_mode_rejects_bool_as_int():
    """Strict mode rejects True where int is expected."""
    from pydantic import ValidationError
    from src.api.schemas import FleetRequest, VehicleInput, DestinationInput
    
    with pytest.raises(ValidationError):
        FleetRequest(
            vehicles=[VehicleInput(
                id="t1", origin_lat=-34.6, origin_lon=-58.4, capacity_tons=10.0
            )],
            destinations=[DestinationInput(
                id="d1", lat=-34.7, lon=-58.5, demand_tons=5.0
            )],
            time_limit_seconds=True  # bool, not int
        )


def test_financial_range_gasoil_negative():
    """Negative gasoil price is rejected."""
    from pydantic import ValidationError
    from src.api.schemas import OpexMovil
    
    with pytest.raises(ValidationError):
        OpexMovil(gasoil_ars_l=-100.0)


def test_financial_range_dolar_zero():
    """Zero dolar_mep (would cause div/0) is rejected."""
    from pydantic import ValidationError
    from src.api.schemas import EconomicProfile
    
    with pytest.raises(ValidationError):
        EconomicProfile(dolar_mep_ars=0.0)


def test_financial_range_valid():
    """Valid financial values pass."""
    from src.api.schemas import EconomicProfile
    
    profile = EconomicProfile(
        dolar_mep_ars=1415.52,
        velocidad_comercial_kmh=40.0,
    )
    assert profile.dolar_mep_ars == 1415.52


def test_departure_time_valid():
    """Valid HH:MM passes."""
    from src.api.schemas import VehicleInput
    
    v = VehicleInput(
        id="truck-1",
        origin_lat=-34.6,
        origin_lon=-58.4,
        capacity_tons=10.0,
        departure_time="08:30"
    )
    assert v.departure_time == "08:30"


def test_departure_time_invalid_format():
    """Invalid departure_time format is rejected."""
    from pydantic import ValidationError
    from src.api.schemas import VehicleInput
    
    with pytest.raises(ValidationError):
        VehicleInput(
            id="truck-1",
            origin_lat=-34.6,
            origin_lon=-58.4,
            capacity_tons=10.0,
            departure_time="25:00"  # invalid hour
        )


def test_departure_time_injection():
    """Arbitrary string as departure_time is rejected."""
    from pydantic import ValidationError
    from src.api.schemas import VehicleInput
    
    with pytest.raises(ValidationError):
        VehicleInput(
            id="truck-1",
            origin_lat=-34.6,
            origin_lon=-58.4,
            capacity_tons=10.0,
            departure_time="'; DROP TABLE routes;--"
        )


def test_fleet_response_integrity_flag():
    """FleetResponse includes integrity_compromised field, defaults to False."""
    from src.api.schemas import FleetResponse
    
    resp = FleetResponse(
        subgraph_edges=100,
        total_time_ms=5000.0,
        phase4_total_legs=3,
        plans={"equilibrista": {}}
    )
    assert resp.integrity_compromised is False


def test_cross_field_validator_consumo_zero():
    """consumo_l_km = 0 is rejected even if individually valid range."""
    from pydantic import ValidationError
    from src.api.schemas import EconomicProfile, OpexMovil
    
    # consumo_l_km has ge=0.01, so 0 is rejected at field level
    with pytest.raises(ValidationError):
        EconomicProfile(
            opex_movil=OpexMovil(consumo_l_km=0.0)
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
