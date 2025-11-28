"""User schemas for request and response validation."""
from pydantic import BaseModel, EmailStr, Field
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


class UserBase(BaseModel):
    """Base user schema."""
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    company_name: str = Field(..., min_length=1, max_length=200)
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8, max_length=100)
    role: UserRole = Field(default=UserRole.MEMBER)
    status: UserStatus = Field(default=UserStatus.ACTIVE)


class UserUpdate(BaseModel):
    """User update schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    company_name: Optional[str] = Field(None, min_length=1, max_length=200)
    avatar_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "company_name": "Acme Corp",
                "avatar_url": "https://example.com/avatar.jpg"
            }
        }


class UserRoleUpdate(BaseModel):
    """User role update schema."""
    role: UserRole


class UserStatusUpdate(BaseModel):
    """User status update schema."""
    status: UserStatus


class UserResponse(UserBase):
    """User response schema."""
    id: str
    status: UserStatus
    role: UserRole
    email_notifications: bool
    push_notifications: bool
    product_updates: bool
    two_factor_enabled: bool
    public_profile: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "John Doe",
                "email": "john@example.com",
                "company_name": "Acme Corp",
                "avatar_url": "https://example.com/avatar.jpg",
                "status": "Active",
                "role": "Member",
                "email_notifications": True,
                "push_notifications": True,
                "product_updates": True,
                "two_factor_enabled": False,
                "public_profile": False,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }


class UserInviteRequest(BaseModel):
    """User invitation request schema."""
    email: EmailStr
    role: UserRole = Field(default=UserRole.MEMBER)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "existinguser@example.com",
                "role": "Member"
            }
        }


class UserSearchQuery(BaseModel):
    """User search query schema."""
    query: str = Field(..., min_length=1)
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "john"
            }
        }
