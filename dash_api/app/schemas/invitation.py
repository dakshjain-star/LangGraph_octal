"""Invitation schemas for request and response validation."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class InvitationStatus(str, Enum):
    """Invitation status enumeration."""
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    EXPIRED = "Expired"


class InvitationResponse(BaseModel):
    """Invitation response schema."""
    id: str
    invitee_email: str
    invitee_user_id: Optional[str] = None
    company_name: str
    company_id: Optional[str] = None
    inviter_id: str
    inviter_name: str
    role: str
    status: InvitationStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "inv123",
                "invitee_email": "user@example.com",
                "company_name": "Acme Corp",
                "inviter_id": "admin123",
                "inviter_name": "John Admin",
                "role": "Member",
                "status": "Pending",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-01T00:00:00Z"
            }
        }


class InvitationActionRequest(BaseModel):
    """Request to accept or decline an invitation."""
    action: str = Field(..., pattern="^(accept|decline)$")
