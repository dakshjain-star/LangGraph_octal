"""Company model for MongoDB."""
from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime


class Company(Document):
    """Company document model for MongoDB."""
    
    name: str = Field(..., min_length=1, max_length=200, unique=True)
    description: Optional[str] = Field(default=None, max_length=500)
    
    # Admin who created the company
    owner_id: str = Field(...)
    owner_name: str = Field(...)
    owner_email: str = Field(...)
    
    # Company settings
    logo_url: Optional[str] = None
    website: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "companies"
        indexes = [
            "name",
            "owner_id",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Acme Corp",
                "description": "A technology company",
                "owner_id": "admin123",
                "owner_name": "John Admin",
                "owner_email": "admin@acme.com",
                "logo_url": "https://example.com/logo.png",
                "website": "https://acme.com"
            }
        }
    
    def to_dict(self) -> dict:
        """Return company as dict."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "owner_name": self.owner_name,
            "owner_email": self.owner_email,
            "logo_url": self.logo_url,
            "website": self.website,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
