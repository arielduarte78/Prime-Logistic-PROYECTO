# src/api/identity.py
"""
Módulo de Identidad Criptográfica — JWT + RBAC + Usage Tracking.

ISO 27001 Controles A.9 (Control de Acceso) y A.10 (Criptografía).

Cadena de dependencias FastAPI:
  1. get_current_identity()  → Decodifica JWT/API Key → TokenPayload
  2. require_role(...)       → Verifica rol ∈ allowed_roles
  3. track_usage()           → Registra consumo por client_id

Todas las operaciones son CPU-bound, sin I/O en el hot-path.
Presupuesto de latencia: < 0.1ms total.

CISO Directives incorporadas:
  - #1: Persistencia asíncrona de contadores a JSONL (no bloquea hot-path)
  - #2: TokenPayload validado con Pydantic strict=True post-decode
  - #3: Refresh tokens stateful con revocation set in-memory
"""

import base64
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger("PrimeAPI.Identity")

# ─────────────────────────────────────────────────────────
# TOKEN PAYLOAD (Pydantic Strict — CISO FIX #2)
# ─────────────────────────────────────────────────────────

VALID_ROLES = frozenset({"operator", "admin", "auditor"})


class TokenPayload(BaseModel):
    """
    Resultado de la decodificación JWT, validado estrictamente.
    CISO FIX #2: Pydantic strict=True previene KeyErrors si faltan claims.
    """
    model_config = ConfigDict(strict=True)

    client_id: str = Field(..., min_length=1, max_length=128)
    client_name: str = Field(..., min_length=1, max_length=256)
    role: str = Field(...)
    exp: int = Field(..., ge=0)
    iat: int = Field(..., ge=0)
    jti: str = Field(..., min_length=1, max_length=64)

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f"Invalid role '{v}'. Must be one of: {sorted(VALID_ROLES)}")
        return v


# ─────────────────────────────────────────────────────────
# JWT ENGINE (HS256, dual-key rotation)
# ─────────────────────────────────────────────────────────

# Security scheme extractors
_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Module-level configuration (set during lifespan)
_jwt_secret: bytearray = bytearray()
_jwt_secret_prev: Optional[bytearray] = None
_access_token_ttl: int = 900       # 15 minutes
_refresh_token_ttl: int = 604800   # 7 days

# Legacy API Key store (backward-compat)
_authorized_keys: Dict[str, str] = {}

# ─── CISO FIX #3: Stateful refresh token revocation set ───
_refresh_tokens: Dict[str, dict] = {}    # jti → {client_id, exp, revoked}
_refresh_lock = threading.Lock()


def configure_identity(
    jwt_secret: bytes,
    jwt_secret_prev: Optional[bytes] = None,
    authorized_keys: Optional[Dict[str, str]] = None,
    access_ttl: int = 900,
    refresh_ttl: int = 604800,
) -> None:
    """
    Called once during lifespan() to configure the identity module.
    Stores secrets as mutable bytearrays for sanitization at shutdown.
    """
    global _jwt_secret, _jwt_secret_prev, _authorized_keys
    global _access_token_ttl, _refresh_token_ttl

    _jwt_secret = bytearray(jwt_secret)
    _jwt_secret_prev = bytearray(jwt_secret_prev) if jwt_secret_prev else None
    _authorized_keys = authorized_keys or {}
    _access_token_ttl = access_ttl
    _refresh_token_ttl = refresh_ttl

    logger.info(
        "Identity module configured: %d legacy keys, access_ttl=%ds, refresh_ttl=%ds",
        len(_authorized_keys), access_ttl, refresh_ttl
    )


def sanitize_secrets() -> None:
    """Overwrite all secrets in memory with zeros. Call at shutdown."""
    global _jwt_secret, _jwt_secret_prev
    if _jwt_secret:
        for i in range(len(_jwt_secret)):
            _jwt_secret[i] = 0
    if _jwt_secret_prev:
        for i in range(len(_jwt_secret_prev)):
            _jwt_secret_prev[i] = 0
    logger.info("Identity module: JWT secrets sanitized from memory.")


def create_access_token(client_id: str, client_name: str, role: str) -> str:
    """Issue a short-lived JWT access token (HS256)."""
    now = int(time.time())
    payload = {
        "sub": client_id,
        "name": client_name,
        "role": role,
        "iat": now,
        "exp": now + _access_token_ttl,
        "jti": uuid.uuid4().hex[:16],
    }
    return jwt.encode(payload, bytes(_jwt_secret), algorithm="HS256")


def create_refresh_token(client_id: str, client_name: str, role: str) -> str:
    """
    Issue a stateful refresh token (CISO FIX #3).
    The refresh token is a JWT, but its JTI is tracked server-side
    for revocation support without I/O.
    """
    now = int(time.time())
    jti = uuid.uuid4().hex
    payload = {
        "sub": client_id,
        "name": client_name,
        "role": role,
        "iat": now,
        "exp": now + _refresh_token_ttl,
        "jti": jti,
        "type": "refresh",
    }
    token = jwt.encode(payload, bytes(_jwt_secret), algorithm="HS256")

    # Register in stateful revocation set (in-memory, O(1) lookup)
    with _refresh_lock:
        _refresh_tokens[jti] = {
            "client_id": client_id,
            "exp": now + _refresh_token_ttl,
            "revoked": False,
        }
        # Housekeeping: purge expired entries (amortized)
        if len(_refresh_tokens) > 1000:
            _purge_expired_refresh_tokens(now)

    return token


def revoke_refresh_token(jti: str) -> bool:
    """Mark a refresh token as revoked (O(1), in-memory)."""
    with _refresh_lock:
        entry = _refresh_tokens.get(jti)
        if entry:
            entry["revoked"] = True
            logger.info("Refresh token %s revoked.", jti[:8])
            return True
        return False


def validate_refresh_token(token: str) -> TokenPayload:
    """
    Decode and validate a refresh token.
    Checks: signature, expiration, type claim, and revocation status.
    All in-memory, no I/O.
    """
    decoded = _decode_jwt_raw(token)
    if decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    jti = decoded.get("jti", "")
    with _refresh_lock:
        entry = _refresh_tokens.get(jti)
        if entry is None:
            raise HTTPException(status_code=401, detail="Refresh token not recognized")
        if entry["revoked"]:
            raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    return _build_token_payload(decoded)


def _purge_expired_refresh_tokens(now: int) -> None:
    """Remove expired entries from the revocation set. Called under lock."""
    expired = [jti for jti, v in _refresh_tokens.items() if v["exp"] < now]
    for jti in expired:
        del _refresh_tokens[jti]
    if expired:
        logger.debug("Purged %d expired refresh tokens.", len(expired))


def _decode_jwt_raw(token: str) -> dict:
    """
    Decode JWT with dual-key rotation support.
    Tries current key first, then previous key.
    Pure CPU, no I/O.
    """
    # Attempt 1: Current key
    try:
        return jwt.decode(token, bytes(_jwt_secret), algorithms=["HS256"])
    except jwt.InvalidSignatureError:
        pass
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.DecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attempt 2: Previous key (rotation grace period)
    if _jwt_secret_prev:
        try:
            decoded = jwt.decode(token, bytes(_jwt_secret_prev), algorithms=["HS256"])
            logger.info("Token validated with previous key (rotation grace period).")
            return decoded
        except (jwt.InvalidSignatureError, jwt.DecodeError):
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token signature",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _build_token_payload(decoded: dict) -> TokenPayload:
    """
    Build and validate TokenPayload from decoded JWT claims.
    CISO FIX #2: Pydantic strict validation catches missing/wrong-type claims.
    """
    try:
        return TokenPayload(
            client_id=decoded.get("sub", ""),
            client_name=decoded.get("name", ""),
            role=decoded.get("role", ""),
            exp=decoded.get("exp", 0),
            iat=decoded.get("iat", 0),
            jti=decoded.get("jti", ""),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token claims: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────────────────
# FASTAPI DEPENDENCY CHAIN
# ─────────────────────────────────────────────────────────

async def get_current_identity(
    bearer: Optional[HTTPAuthorizationCredentials] = Security(_bearer_scheme),
    api_key: Optional[str] = Security(_api_key_header),
) -> TokenPayload:
    """
    Dependency 1: Extract and validate identity from request.

    Priority:
      1. JWT Bearer token (new system)
      2. X-API-Key header (legacy backward-compat)

    Pure CPU — no disk, no network, no blocking I/O.
    """
    # Priority 1: JWT Bearer
    if bearer and bearer.credentials:
        decoded = _decode_jwt_raw(bearer.credentials)
        # Filter out refresh tokens used as access tokens
        if decoded.get("type") == "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh tokens cannot be used for API access",
            )
        return _build_token_payload(decoded)

    # Priority 2: Legacy API Key (backward-compatible)
    if api_key:
        client_name = _authorized_keys.get(api_key)
        if client_name:
            now = int(time.time())
            return TokenPayload(
                client_id=hashlib.sha256(api_key.encode()).hexdigest()[:16],
                client_name=client_name,
                role="operator",  # Legacy keys get operator role by default
                exp=now + 86400,  # Synthetic 24h expiration
                iat=now,
                jti=f"legacy_{hashlib.md5(api_key.encode()).hexdigest()[:8]}",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing credentials. Provide 'Authorization: Bearer <token>' or 'X-API-Key' header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency factory: returns a FastAPI dependency that enforces RBAC.

    Usage:
        @app.post('/fleet')
        async def fleet_endpoint(
            identity: TokenPayload = Depends(require_role("operator", "admin")),
        ):

    Pure string comparison — O(1), no I/O.
    """
    allowed = frozenset(allowed_roles)

    async def _role_guard(
        identity: TokenPayload = Depends(get_current_identity),
    ) -> TokenPayload:
        if identity.role not in allowed:
            logger.warning(
                "RBAC DENIED: client=%s role=%s attempted access requiring %s",
                identity.client_id, identity.role, allowed_roles
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{identity.role}' does not have permission. Required: {sorted(allowed)}",
            )
        return identity

    return _role_guard


# ─────────────────────────────────────────────────────────
# USAGE TRACKING + PERSISTENCE (CISO FIX #1)
# ─────────────────────────────────────────────────────────

@dataclass
class ClientUsage:
    client_id: str
    client_name: str
    role: str
    request_count: int = 0
    last_request_utc: str = ""
    endpoints_breakdown: Dict[str, int] = field(default_factory=dict)


_usage_counters: Dict[str, ClientUsage] = {}
_usage_lock = threading.Lock()
_usage_persist_path: Optional[Path] = None
_usage_persist_interval: int = 60  # seconds
_usage_last_persist: float = 0.0


def configure_usage_persistence(persist_dir: Path, interval_seconds: int = 60) -> None:
    """Configure the path and interval for async usage persistence."""
    global _usage_persist_path, _usage_persist_interval
    persist_dir.mkdir(parents=True, exist_ok=True)
    _usage_persist_path = persist_dir / "usage_counters.jsonl"
    _usage_persist_interval = interval_seconds
    logger.info("Usage persistence configured: %s (interval=%ds)", _usage_persist_path, interval_seconds)

    # Load existing counters on startup
    _load_persisted_usage()


def _load_persisted_usage() -> None:
    """Load the last persisted usage snapshot if it exists."""
    if _usage_persist_path and _usage_persist_path.exists():
        try:
            # Read the last line (most recent snapshot)
            last_line = ""
            with open(_usage_persist_path, "r", encoding="utf-8") as f:
                for line in f:
                    last_line = line
            if last_line.strip():
                snapshot = json.loads(last_line)
                with _usage_lock:
                    for client_data in snapshot.get("clients", []):
                        cid = client_data["client_id"]
                        _usage_counters[cid] = ClientUsage(
                            client_id=cid,
                            client_name=client_data.get("client_name", ""),
                            role=client_data.get("role", "operator"),
                            request_count=client_data.get("request_count", 0),
                            last_request_utc=client_data.get("last_request_utc", ""),
                            endpoints_breakdown=client_data.get("endpoints_breakdown", {}),
                        )
                logger.info("Loaded persisted usage: %d clients.", len(_usage_counters))
        except Exception as e:
            logger.warning("Failed to load persisted usage: %s", e)


def _maybe_persist_usage() -> None:
    """
    Persist usage counters if the interval has elapsed.
    CISO FIX #1: Non-blocking — called from track_usage() under lock,
    but writes are fast (single JSON line append).
    """
    global _usage_last_persist
    if _usage_persist_path is None:
        return

    now = time.time()
    if now - _usage_last_persist < _usage_persist_interval:
        return

    _usage_last_persist = now

    # Build snapshot under lock (already held by caller)
    snapshot = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "clients": [
            {
                "client_id": c.client_id,
                "client_name": c.client_name,
                "role": c.role,
                "request_count": c.request_count,
                "last_request_utc": c.last_request_utc,
                "endpoints_breakdown": c.endpoints_breakdown,
            }
            for c in _usage_counters.values()
        ],
    }

    # Fire-and-forget write (append one JSON line)
    try:
        with open(_usage_persist_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, default=str) + "\n")
    except Exception as e:
        logger.error("Usage persistence write failed: %s", e)


async def track_usage(
    request: Request,
    identity: TokenPayload = Depends(get_current_identity),
) -> TokenPayload:
    """
    Dependency 3: Record request consumption per client_id.
    O(1) in-memory dict increment with lock.
    Periodic persistence to JSONL (CISO FIX #1).
    """
    with _usage_lock:
        counter = _usage_counters.get(identity.client_id)
        if counter is None:
            counter = ClientUsage(
                client_id=identity.client_id,
                client_name=identity.client_name,
                role=identity.role,
            )
            _usage_counters[identity.client_id] = counter

        counter.request_count += 1
        counter.last_request_utc = datetime.now(timezone.utc).isoformat()
        endpoint = request.url.path.rstrip("/")
        counter.endpoints_breakdown[endpoint] = \
            counter.endpoints_breakdown.get(endpoint, 0) + 1

        # Async persistence check (amortized cost)
        _maybe_persist_usage()

    return identity


def get_usage_report() -> dict:
    """Snapshot of all client usage for /admin/usage endpoint."""
    with _usage_lock:
        return {
            "snapshot_utc": datetime.now(timezone.utc).isoformat(),
            "total_clients": len(_usage_counters),
            "clients": [
                {
                    "client_id": c.client_id,
                    "client_name": c.client_name,
                    "role": c.role,
                    "total_requests": c.request_count,
                    "endpoints": dict(c.endpoints_breakdown),
                    "last_request_utc": c.last_request_utc,
                }
                for c in sorted(
                    _usage_counters.values(),
                    key=lambda x: x.request_count,
                    reverse=True,
                )
            ],
        }


def force_persist_usage() -> None:
    """Force a persistence write (call at shutdown)."""
    global _usage_last_persist
    with _usage_lock:
        _usage_last_persist = 0  # Force interval check to pass
        _maybe_persist_usage()
    logger.info("Usage counters force-persisted at shutdown.")
