"""Task History model for MongoDB."""
from beanie import Document
from pydantic import Field
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class HistoryActionType(str, Enum):
    """History action type enumeration."""
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    PRIORITY_CHANGED = "priority_changed"
    ASSIGNEE_CHANGED = "assignee_changed"
    DUE_DATE_CHANGED = "due_date_changed"
    PROJECT_CHANGED = "project_changed"
    TITLE_CHANGED = "title_changed"
    DESCRIPTION_CHANGED = "description_changed"
    COLLABORATORS_CHANGED = "collaborators_changed"


class TaskHistory(Document):
    """Task History document model for MongoDB."""
    
    task_id: str = Field(..., description="Reference to the task")
    
    # Action info
    action: HistoryActionType = Field(..., description="Type of action performed")
    field_name: Optional[str] = Field(default=None, description="Name of the field that was changed")
    old_value: Optional[Any] = Field(default=None, description="Previous value")
    new_value: Optional[Any] = Field(default=None, description="New value")
    
    # Who made the change
    user_id: str = Field(..., description="ID of user who made the change")
    user_name: str = Field(..., description="Name of user who made the change")
    user_avatar: Optional[str] = Field(default=None, description="Avatar of user who made the change")
    
    # Company info for multi-tenancy
    company_id: Optional[str] = Field(default=None, description="Company this history belongs to")
    
    # Timestamps - stored in UTC
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "task_history"
        indexes = [
            "task_id",
            "company_id",
            "user_id",
            "action",
            "created_at",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "507f1f77bcf86cd799439011",
                "action": "status_changed",
                "field_name": "status",
                "old_value": "To Do",
                "new_value": "In Progress",
                "user_id": "507f1f77bcf86cd799439012",
                "user_name": "John Doe",
                "user_avatar": "https://example.com/avatar.jpg",
                "company_id": "507f1f77bcf86cd799439013",
                "created_at": "2024-01-15T10:30:00Z"
            }
        }
