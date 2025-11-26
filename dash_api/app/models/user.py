"""User model for MongoDB."""
from beanie import Document
from pydantic import EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class UserStatus(str, Enum):
    """User status enumeration."""
    ACTIVE = "Active"
    INVITED = "Invited"


class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "Admin"
    MEMBER = "Member"
    VIEWER = "Viewer"


class User(Document):
    """User document model for MongoDB."""
    
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr = Field(..., unique=True)
    password_hash: str = Field(...)
    company_name: str = Field(..., min_length=1, max_length=200)
    avatar_url: Optional[str] = None
    status: UserStatus = Field(default=UserStatus.ACTIVE)
    role: UserRole = Field(default=UserRole.MEMBER)
    
    # Settings
    email_notifications: bool = Field(default=True)
    push_notifications: bool = Field(default=True)
    product_updates: bool = Field(default=True)
    two_factor_enabled: bool = Field(default=False)
    public_profile: bool = Field(default=False)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "users"
        indexes = [
            "email",
            "status",
            "role",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john@example.com",
                "company_name": "Acme Corp",
                "avatar_url": "https://example.com/avatar.jpg",
                "status": "Active",
                "role": "Member"
            }
        }
    
    def dict_without_password(self) -> dict:
        """Return user dict without password_hash field."""
        user_dict = self.dict()
        user_dict.pop("password_hash", None)
        return user_dict
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
