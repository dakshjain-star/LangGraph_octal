"""User model for MongoDB."""
from beanie import Document
from pydantic import EmailStr, Field
from typing import Optional, List
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
    
    # Legacy single company field (for backward compatibility with existing data)
    company_id: Optional[str] = Field(default=None)
    company_name: Optional[str] = Field(default=None)
    
    # Company associations - user can belong to multiple companies
    company_ids: List[str] = Field(default_factory=list)  # List of Company IDs
    company_names: List[str] = Field(default_factory=list)  # List of Company names
    
    # Current active company (the one user is currently working in)
    current_company_id: Optional[str] = Field(default=None)
    current_company_name: Optional[str] = Field(default=None)
    
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
            "company_ids",
            "current_company_id",
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
        # Get effective company ID (prefer new field, fallback to legacy)
        effective_company_id = self.current_company_id or self.company_id
        effective_company_ids = self.company_ids if self.company_ids else ([self.company_id] if self.company_id else [])
        effective_company_names = self.company_names if self.company_names else ([self.company_name] if self.company_name else [])
        
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "company_ids": effective_company_ids,
            "company_names": effective_company_names,
            "current_company_id": effective_company_id,
            "current_company_name": self.current_company_name or self.company_name,
            # For backward compatibility
            "company_id": effective_company_id,
            "company_name": ", ".join(effective_company_names) if effective_company_names else "Individual",
            "avatar_url": self.avatar_url,
            "status": self.status,
            "role": self.role,
            "email_notifications": self.email_notifications,
            "push_notifications": self.push_notifications,
            "product_updates": self.product_updates,
            "two_factor_enabled": self.two_factor_enabled,
            "public_profile": self.public_profile,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    def get_effective_company_id(self) -> Optional[str]:
        """Get the effective current company ID (supports old and new schema)."""
        return self.current_company_id or self.company_id
    
    def get_effective_company_ids(self) -> List[str]:
        """Get all company IDs the user belongs to (supports old and new schema)."""
        if self.company_ids:
            return self.company_ids
        elif self.company_id:
            return [self.company_id]
        return []
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
