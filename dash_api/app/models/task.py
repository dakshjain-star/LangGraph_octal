"""Task model for MongoDB."""
from beanie import Document
from pydantic import Field
from typing import Optional
from datetime import datetime, date
from enum import Enum


class TaskStatus(str, Enum):
    """Task status enumeration."""
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    REVIEW = "Review"
    DONE = "Done"


class TaskPriority(str, Enum):
    """Task priority enumeration."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Task(Document):
    """Task document model for MongoDB."""
    
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    status: TaskStatus = Field(default=TaskStatus.TODO)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    due_date: Optional[datetime] = None  # Use datetime for Beanie compatibility
    
    # Assignee info (denormalized for performance)
    assignee_id: str = Field(...)
    assignee_name: str = Field(...)
    assignee_avatar: Optional[str] = None
    
    # Creator info
    creator_id: str = Field(...)
    
    # Company info (for multi-tenancy)
    company_id: Optional[str] = Field(default=None)  # Reference to Company
    company_name: Optional[str] = Field(default=None, max_length=200)
    
    # Project info (optional, denormalized)
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "tasks"
        indexes = [
            "assignee_id",
            "creator_id",
            "company_id",
            "project_id",
            "status",
            "priority",
            "due_date",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "In Progress",
                "priority": "High",
                "due_date": "2024-06-15",
                "assignee_id": "user123",
                "assignee_name": "John Doe",
                "assignee_avatar": "https://example.com/avatar.jpg",
                "creator_id": "user456",
                "project_id": "proj789",
                "project_name": "API Development"
            }
        }
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
    
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if self.due_date and self.status != TaskStatus.DONE:
            return datetime.utcnow().date() > self.due_date.date()
        return False
