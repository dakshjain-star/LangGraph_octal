"""Authentication dependency for chatbot endpoints."""
import logging
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Security scheme reused by endpoints
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Validate JWT token using dash_api's authentication.
    Returns user info extracted from the token.
    """
    if not credentials:
        logger.warning("No credentials provided in request")
        raise HTTPException(
            status_code=401,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # Use dash_api's token verification
    from dash_api.app.services.auth import verify_token as dash_verify_token

    payload = dash_verify_token(token, token_type="access")
    if not payload:
        logger.warning(f"Token verification failed")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get full user info from database
    from dash_api.app.models.user import User
    user = await User.get(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "email": user.email,
        "company_id": user.get_effective_company_id(),
        "company_name": user.current_company_name or user.company_name,
        "role": user.role.value if user.role else "Member"
    }
