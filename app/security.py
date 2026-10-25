from __future__ import annotations

import hmac
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.config import settings

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def verify_admin_api_key(
    x_admin_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(None),
) -> bool:
    """
    Verifies that the caller possesses the configured administrator key.
    Accepts either 'X-Admin-Key: <key>' or 'Authorization: Bearer <key>'.
    Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
    """
    provided_key: Optional[str] = x_admin_key

    if not provided_key and authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided_key = parts[1].strip()

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin credentials. Provide header 'X-Admin-Key' or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant time comparison
    if not hmac.compare_digest(provided_key, settings.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid administrative credentials.",
        )

    return True
