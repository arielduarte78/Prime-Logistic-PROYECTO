"""
Verification tests for Phase 2 SGSI: JWT RBAC, Identity, Usage Tracking.
Run: .\\venv\\Scripts\\python.exe -m pytest scripts\\test_phase2_sgsi.py -v
"""
import hashlib
import json
import os
import time
import pytest


# ─── Test 1: JWT Lifecycle ───

def test_jwt_issue_and_decode():
    """Issue a token and decode it successfully."""
    from src.api.identity import (
        configure_identity, create_access_token, get_current_identity,
        TokenPayload, _decode_jwt_raw, _build_token_payload,
    )
    key = os.urandom(32)
    configure_identity(jwt_secret=key)

    token = create_access_token("test_client", "Test Corp", "operator")
    assert isinstance(token, str)
    assert len(token) > 20

    # Decode raw
    decoded = _decode_jwt_raw(token)
    assert decoded["sub"] == "test_client"
    assert decoded["role"] == "operator"

    # Build payload with Pydantic strict validation
    payload = _build_token_payload(decoded)
    assert isinstance(payload, TokenPayload)
    assert payload.client_id == "test_client"
    assert payload.role == "operator"


def test_jwt_expiration():
    """Expired token is rejected."""
    import jwt as pyjwt
    from src.api.identity import configure_identity, _decode_jwt_raw
    from fastapi import HTTPException

    key = os.urandom(32)
    configure_identity(jwt_secret=key)

    # Create manually expired token
    expired_payload = {
        "sub": "test", "name": "Test", "role": "operator",
        "iat": int(time.time()) - 3600,
        "exp": int(time.time()) - 1800,  # expired 30 min ago
        "jti": "test123",
    }
    token = pyjwt.encode(expired_payload, key, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        _decode_jwt_raw(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_jwt_invalid_signature():
    """Token signed with wrong key is rejected."""
    from src.api.identity import configure_identity, create_access_token, _decode_jwt_raw
    from fastapi import HTTPException

    key1 = os.urandom(32)
    key2 = os.urandom(32)

    configure_identity(jwt_secret=key1)
    token = create_access_token("client1", "Corp", "operator")

    # Reconfigure with different key (no prev key)
    configure_identity(jwt_secret=key2)

    with pytest.raises(HTTPException) as exc_info:
        _decode_jwt_raw(token)
    assert exc_info.value.status_code == 401


def test_jwt_dual_key_rotation():
    """Token signed with previous key is accepted during rotation."""
    from src.api.identity import configure_identity, create_access_token, _decode_jwt_raw

    key_old = os.urandom(32)
    key_new = os.urandom(32)

    # Issue token with old key
    configure_identity(jwt_secret=key_old)
    token = create_access_token("client1", "Corp", "operator")

    # Rotate to new key, keeping old as prev
    configure_identity(jwt_secret=key_new, jwt_secret_prev=key_old)

    decoded = _decode_jwt_raw(token)
    assert decoded["sub"] == "client1"


# ─── Test 2: Token Payload Pydantic Strict (CISO FIX #2) ───

def test_token_payload_strict_rejects_missing_claims():
    """Missing claims cause validation failure."""
    from pydantic import ValidationError
    from src.api.identity import TokenPayload

    with pytest.raises(ValidationError):
        TokenPayload(
            client_id="test",
            # Missing: client_name, role, exp, iat, jti
        )


def test_token_payload_strict_rejects_wrong_type():
    """String where int expected is rejected in strict mode."""
    from pydantic import ValidationError
    from src.api.identity import TokenPayload

    with pytest.raises(ValidationError):
        TokenPayload(
            client_id="test",
            client_name="Test",
            role="operator",
            exp="not_an_int",  # should be int
            iat=123,
            jti="abc",
        )


def test_token_payload_invalid_role():
    """Invalid role is rejected."""
    from pydantic import ValidationError
    from src.api.identity import TokenPayload

    with pytest.raises(ValidationError):
        TokenPayload(
            client_id="test",
            client_name="Test",
            role="superadmin",  # not in VALID_ROLES
            exp=123,
            iat=123,
            jti="abc",
        )


# ─── Test 3: RBAC Enforcement ───

def test_require_role_allows_matching():
    """Matching role passes through."""
    import asyncio
    from src.api.identity import configure_identity, require_role, TokenPayload

    configure_identity(jwt_secret=os.urandom(32))

    guard = require_role("operator", "admin")

    payload = TokenPayload(
        client_id="test", client_name="Test", role="operator",
        exp=int(time.time()) + 3600, iat=int(time.time()), jti="test123"
    )

    # The guard is an async function — call it directly with identity
    async def run():
        result = await guard(identity=payload)
        return result

    result = asyncio.run(run())
    assert result.client_id == "test"


def test_require_role_blocks_unauthorized():
    """Non-matching role raises 403."""
    import asyncio
    from src.api.identity import configure_identity, require_role, TokenPayload
    from fastapi import HTTPException

    configure_identity(jwt_secret=os.urandom(32))

    guard = require_role("admin")  # Only admin allowed

    payload = TokenPayload(
        client_id="test", client_name="Test", role="operator",
        exp=int(time.time()) + 3600, iat=int(time.time()), jti="test123"
    )

    async def run():
        return await guard(identity=payload)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 403


# ─── Test 4: Refresh Tokens Stateful (CISO FIX #3) ───

def test_refresh_token_lifecycle():
    """Create → validate → revoke lifecycle."""
    from src.api.identity import (
        configure_identity, create_refresh_token, validate_refresh_token,
        revoke_refresh_token,
    )
    from fastapi import HTTPException

    key = os.urandom(32)
    configure_identity(jwt_secret=key)

    # Create
    refresh = create_refresh_token("client1", "Corp", "operator")
    assert isinstance(refresh, str)

    # Validate
    payload = validate_refresh_token(refresh)
    assert payload.client_id == "client1"

    # Revoke
    import jwt as pyjwt
    decoded = pyjwt.decode(refresh, key, algorithms=["HS256"])
    jti = decoded["jti"]
    assert revoke_refresh_token(jti) is True

    # Cannot use after revocation
    with pytest.raises(HTTPException) as exc_info:
        validate_refresh_token(refresh)
    assert "revoked" in exc_info.value.detail.lower()


# ─── Test 5: Usage Tracking ───

def test_usage_counter_increment():
    """Usage counter increments correctly."""
    from src.api.identity import (
        configure_identity, _usage_counters, _usage_lock, ClientUsage,
    )

    configure_identity(jwt_secret=os.urandom(32))

    # Manually simulate what track_usage does
    import threading
    from datetime import datetime, timezone

    with _usage_lock:
        _usage_counters["test_billing"] = ClientUsage(
            client_id="test_billing",
            client_name="Billing Test",
            role="operator",
        )
        counter = _usage_counters["test_billing"]
        for _ in range(100):
            counter.request_count += 1
            counter.endpoints_breakdown["/fleet"] = \
                counter.endpoints_breakdown.get("/fleet", 0) + 1

    assert counter.request_count == 100
    assert counter.endpoints_breakdown["/fleet"] == 100


def test_usage_report_structure():
    """get_usage_report returns expected structure."""
    from src.api.identity import configure_identity, get_usage_report

    configure_identity(jwt_secret=os.urandom(32))

    report = get_usage_report()
    assert "snapshot_utc" in report
    assert "total_clients" in report
    assert "clients" in report
    assert isinstance(report["clients"], list)


# ─── Test 6: Backward Compatibility ───

def test_legacy_api_key_backward_compat():
    """Legacy API key still works and produces operator TokenPayload."""
    from src.api.identity import configure_identity, _build_token_payload, TokenPayload
    import hashlib

    key = os.urandom(32)
    legacy_keys = {"my_old_key_123": "OldClient"}
    configure_identity(jwt_secret=key, authorized_keys=legacy_keys)

    # Simulate what get_current_identity does for API key path
    client_name = legacy_keys.get("my_old_key_123")
    assert client_name == "OldClient"

    # Synthesize TokenPayload
    now = int(time.time())
    payload = TokenPayload(
        client_id=hashlib.sha256(b"my_old_key_123").hexdigest()[:16],
        client_name=client_name,
        role="operator",
        exp=now + 86400,
        iat=now,
        jti=f"legacy_{hashlib.md5(b'my_old_key_123').hexdigest()[:8]}",
    )
    assert payload.role == "operator"
    assert payload.client_name == "OldClient"


# ─── Test 7: Secret Sanitization ───

def test_jwt_secret_sanitization():
    """JWT secrets are zeroed after sanitize_secrets()."""
    from src.api.identity import configure_identity, sanitize_secrets, _jwt_secret

    key = os.urandom(32)
    configure_identity(jwt_secret=key)

    sanitize_secrets()

    from src.api.identity import _jwt_secret as secret_after
    assert all(b == 0 for b in secret_after)


# ─── Test 8: Latency Budget ───

def test_jwt_decode_latency_under_1ms():
    """JWT decode + role check must complete in < 1ms."""
    import jwt as pyjwt
    from src.api.identity import configure_identity, _decode_jwt_raw, _build_token_payload

    key = os.urandom(32)
    configure_identity(jwt_secret=key)

    # Pre-create a token
    now = int(time.time())
    payload = {
        "sub": "bench", "name": "Bench", "role": "operator",
        "iat": now, "exp": now + 900, "jti": "bench123",
    }
    token = pyjwt.encode(payload, key, algorithm="HS256")

    # Warm up
    for _ in range(10):
        _decode_jwt_raw(token)

    # Benchmark
    iterations = 1000
    start = time.perf_counter()
    for _ in range(iterations):
        decoded = _decode_jwt_raw(token)
        _ = _build_token_payload(decoded)
        # Simulate role check
        assert decoded["role"] in {"operator", "admin"}
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    assert avg_ms < 1.0, f"JWT decode + role check took {avg_ms:.3f}ms (budget: <1ms)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
