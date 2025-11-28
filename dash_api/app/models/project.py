"""Project model for MongoDB."""
from beanie import Document, Link
from pydantic import Field
from typing import Optional
from datetime import datetime
from enum import Enum


class ProjectStatus(str, Enum):
    """Project status enumeration."""
    ACTIVE = "Active"
    ARCHIVED = "Archived"
    ON_HOLD = "On Hold"


class Project(Document):
    """Project document model for MongoDB."""
    
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE)
    due_date: Optional[datetime] = None
    
    # Owner info (denormalized for performance)
    owner_id: str = Field(...)
    owner_name: str = Field(...)
    
    # Client info
    client_name: str = Field(..., min_length=1, max_length=200)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "projects"
        indexes = [
            "owner_id",
            "status",
            "due_date",
            "client_name",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Website Redesign",
                "description": "Complete overhaul of company website",
                "status": "Active",
                "due_date": "2024-12-31",
                "owner_id": "user123",
                "owner_name": "John Doe",
                "client_name": "Acme Corp"
            }
        }
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
