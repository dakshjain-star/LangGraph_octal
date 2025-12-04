"""Task History schemas for request and response validation."""
from pydantic import BaseModel, Field
from typing import Optional, Any, List
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


class TaskHistoryResponse(BaseModel):
    """Task History response schema."""
    id: str
    task_id: str
    action: HistoryActionType
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    user_id: str
    user_name: str
    user_avatar: Optional[str] = None
    company_id: Optional[str] = None
    created_at: datetime
    # IST timestamp string for display
    created_at_ist: str = Field(default="")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "task_id": "507f1f77bcf86cd799439012",
                "action": "status_changed",
                "field_name": "status",
                "old_value": "To Do",
                "new_value": "In Progress",
                "user_id": "507f1f77bcf86cd799439013",
                "user_name": "John Doe",
                "user_avatar": "https://example.com/avatar.jpg",
                "company_id": "507f1f77bcf86cd799439014",
                "created_at": "2024-01-15T10:30:00Z",
                "created_at_ist": "15 Jan 2024, 04:00 PM IST"
            }
        }


class TaskHistoryListResponse(BaseModel):
    """Task History list response schema."""
    history: List[TaskHistoryResponse]
    total: int
