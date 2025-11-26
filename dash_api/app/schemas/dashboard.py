"""Dashboard schemas for analytics and statistics."""
from pydantic import BaseModel
from typing import List
from app.schemas.project import ProjectResponse
from app.schemas.task import TaskResponse


class DashboardStats(BaseModel):
    """Dashboard statistics schema."""
    tasks_completed: int = 0
    pending_tasks: int = 0
    high_priority_tasks: int = 0
    active_projects: int = 0
    overdue_tasks: int = 0
    tasks_in_progress: int = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "tasks_completed": 45,
                "pending_tasks": 12,
                "high_priority_tasks": 5,
                "active_projects": 8,
                "overdue_tasks": 3,
                "tasks_in_progress": 7
            }
        }


class DashboardData(BaseModel):
    """Complete dashboard data schema."""
    stats: DashboardStats
    recent_projects: List[ProjectResponse]
    my_tasks: List[TaskResponse]
    
    class Config:
        json_schema_extra = {
            "example": {
                "stats": {
                    "tasks_completed": 45,
                    "pending_tasks": 12,
                    "high_priority_tasks": 5,
                    "active_projects": 8
                },
                "recent_projects": [],
                "my_tasks": []
            }
        }


class SettingsUpdate(BaseModel):
    """User settings update schema."""
    email_notifications: bool = None
    push_notifications: bool = None
    product_updates: bool = None
    two_factor_enabled: bool = None
    public_profile: bool = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "email_notifications": True,
                "push_notifications": False,
                "product_updates": True,
                "two_factor_enabled": False,
                "public_profile": False
            }
        }


class SettingsResponse(BaseModel):
    """User settings response schema."""
    email_notifications: bool
    push_notifications: bool
    product_updates: bool
    two_factor_enabled: bool
    public_profile: bool
    
    class Config:
        from_attributes = True
