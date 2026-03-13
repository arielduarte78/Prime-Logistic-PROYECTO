#src/api/security.py
import os
import time
import logging
from typing import Dict
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger("PrimeAPI.Security")

# Dependency for API Key validation
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# In-memory Rate Limiter state
# Dictionary mapping API Key to a list of timestamps (floats)
_rate_limit_state: Dict[str, list[float]] = {}

# Cachear al importar el módulo, no por cada request
_AUTHORIZED_KEYS: Dict[str, str] = {}

def _load_authorized_keys() -> Dict[str, str]:
    """
    Returns a dictionary of allowed API keys mapped to client names.
    Expects format: 'cliente1:clave1,cliente2:clave2'
    """
    keys_str = os.getenv("PRIME_API_KEYS")
    
    if not keys_str:
        logger.warning("SECURITY WARNING: PRIME_API_KEYS not found. Using default DEV keys.")
        return {"dev_key_123": "dev_client"}
        
    result = {}
    for pair in keys_str.split(","):
        if ":" in pair:
            client, key = pair.split(":", 1)
            result[key.strip()] = client.strip()
            
    return result

_AUTHORIZED_KEYS = _load_authorized_keys()

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Validates the API Key and returns the associated API Key string if valid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        
    authorized_keys = _AUTHORIZED_KEYS
    
    client_name = authorized_keys.get(api_key)
    if not client_name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        
    return api_key

def _check_rate_limit(api_key: str, max_requests: int, window_seconds: int = 60) -> None:
    """
    Generic rate limiter checking timestamps.
    Raises HTTPException 429 if the limit is exceeded.
    """
    current_time = time.time()
    
    if api_key not in _rate_limit_state:
        _rate_limit_state[api_key] = []
        
    # Clean up old timestamps to prevent memory leaks
    _rate_limit_state[api_key] = [
        ts for ts in _rate_limit_state[api_key] 
        if current_time - ts < window_seconds
    ]
    
    if len(_rate_limit_state[api_key]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Maximum {max_requests} requests per {window_seconds} seconds."
        )
        
    # Register the new request
    _rate_limit_state[api_key].append(current_time)

# Rate limiting handled by slowapi in main.py
