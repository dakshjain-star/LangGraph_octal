"""Task schemas for request and response validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
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


class TaskBase(BaseModel):
    """Base task schema."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    due_date: Optional[date] = None
    project_id: Optional[str] = None


class TaskCreate(TaskBase):
    """Task creation schema."""
    assignee_id: str
    status: TaskStatus = Field(default=TaskStatus.TODO)
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "To Do",
                "priority": "High",
                "due_date": "2024-06-15",
                "assignee_id": "507f1f77bcf86cd799439011",
                "project_id": "507f1f77bcf86cd799439012"
            }
        }


class TaskUpdate(BaseModel):
    """Task update schema."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[date] = None
    assignee_id: Optional[str] = None
    project_id: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    """Task status update schema."""
    status: TaskStatus


class TaskAssigneeUpdate(BaseModel):
    """Task assignee update schema."""
    assignee_id: str


class TaskResponse(TaskBase):
    """Task response schema."""
    id: str
    status: TaskStatus
    assignee_id: str
    assignee_name: str
    assignee_avatar: Optional[str]
    creator_id: str
    project_name: Optional[str]
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "title": "Implement user authentication",
                "description": "Add JWT-based authentication to the API",
                "status": "In Progress",
                "priority": "High",
                "due_date": "2024-06-15",
                "assignee_id": "507f1f77bcf86cd799439012",
                "assignee_name": "John Doe",
                "assignee_avatar": "https://example.com/avatar.jpg",
                "creator_id": "507f1f77bcf86cd799439013",
                "project_id": "507f1f77bcf86cd799439014",
                "project_name": "API Development",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "is_overdue": False
            }
        }


class TaskFilter(BaseModel):
    """Task filter schema for complex queries."""
    assignee_id: Optional[str] = None
    creator_id: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[List[TaskStatus]] = None
    priority: Optional[List[TaskPriority]] = None
    search: Optional[str] = None
    date_filter: Optional[str] = "all"  # all, today, this_week, overdue
    sort_by: Optional[str] = "created_at"  # created_at, due_date, priority
    sort_order: Optional[str] = "desc"  # asc, desc
    skip: int = 0
    limit: int = 50
    all_companies: bool = False  # If True, show tasks from all companies user belongs to
    
    class Config:
        json_schema_extra = {
            "example": {
                "assignee_id": "507f1f77bcf86cd799439011",
                "status": ["To Do", "In Progress"],
                "priority": ["High"],
                "project_id": "507f1f77bcf86cd799439012",
                "search": "authentication",
                "date_filter": "this_week",
                "sort_by": "due_date",
                "sort_order": "asc",
                "skip": 0,
                "limit": 20
            }
        }


class TaskWithComments(TaskResponse):
    """Task response with comments."""
    comments: List[dict] = []
