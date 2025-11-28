"""Invitation model for MongoDB."""
from beanie import Document
from pydantic import EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class InvitationStatus(str, Enum):
    """Invitation status enumeration."""
    PENDING = "Pending"
    ACCEPTED = "Accepted"
    DECLINED = "Declined"
    EXPIRED = "Expired"


class Invitation(Document):
    """Invitation document model for MongoDB."""
    
    # The user being invited (by email)
    invitee_email: EmailStr = Field(...)
    invitee_user_id: Optional[str] = None  # Set when user exists
    
    # The company/admin sending the invitation
    company_id: Optional[str] = None  # Reference to Company (optional for legacy data)
    company_name: str = Field(..., min_length=1, max_length=200)
    inviter_id: str = Field(...)  # The admin who sent the invite
    inviter_name: str = Field(...)
    
    # Role to be assigned upon acceptance
    role: str = Field(default="Member")
    
    # Status tracking
    status: InvitationStatus = Field(default=InvitationStatus.PENDING)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    class Settings:
        name = "invitations"
        indexes = [
            "invitee_email",
            "inviter_id",
            "status",
            "company_id",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "invitee_email": "user@example.com",
                "company_name": "Acme Corp",
                "inviter_id": "admin123",
                "inviter_name": "John Admin",
                "role": "Member",
                "status": "Pending"
            }
        }
    
    def to_dict(self) -> dict:
        """Return invitation as dict."""
        return {
            "id": str(self.id),
            "invitee_email": self.invitee_email,
            "invitee_user_id": self.invitee_user_id,
            "company_name": self.company_name,
            "company_id": self.company_id,
            "inviter_id": self.inviter_id,
            "inviter_name": self.inviter_name,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }
