"""Project schemas for request and response validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


class ProjectStatus(str, Enum):
    """Project status enumeration."""
    ACTIVE = "Active"
    ARCHIVED = "Archived"
    ON_HOLD = "On Hold"


class ProjectBase(BaseModel):
    """Base project schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    client_name: str = Field(..., min_length=1, max_length=200)
    due_date: Optional[date] = None


class ProjectCreate(ProjectBase):
    """Project creation schema."""
    owner_id: str
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Website Redesign",
                "description": "Complete overhaul of company website",
                "client_name": "Acme Corp",
                "due_date": "2024-12-31",
                "owner_id": "507f1f77bcf86cd799439011",
                "status": "Active"
            }
        }


class ProjectUpdate(BaseModel):
    """Project update schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    client_name: Optional[str] = Field(None, min_length=1, max_length=200)
    due_date: Optional[date] = None
    status: Optional[ProjectStatus] = None
    owner_id: Optional[str] = None


class ProjectStatusUpdate(BaseModel):
    """Project status update schema."""
    status: ProjectStatus


class ProjectResponse(ProjectBase):
    """Project response schema."""
    id: str
    status: ProjectStatus
    owner_id: str
    owner_name: str
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Website Redesign",
                "description": "Complete overhaul of company website",
                "status": "Active",
                "due_date": "2024-12-31",
                "owner_id": "507f1f77bcf86cd799439012",
                "owner_name": "John Doe",
                "client_name": "Acme Corp",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }


class ProjectFilter(BaseModel):
    """Project filter schema."""
    status: Optional[List[ProjectStatus]] = None
    owner_id: Optional[str] = None
    client_name: Optional[str] = None
    company_id: Optional[str] = None
    all_companies: Optional[bool] = False
    search: Optional[str] = None
    sort_by: Optional[str] = "created_at"  # created_at, due_date
    sort_order: Optional[str] = "desc"  # asc, desc
    skip: int = 0
    limit: int = 50
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": ["Active", "On Hold"],
                "owner_id": "507f1f77bcf86cd799439011",
                "client_name": "Acme",
                "search": "website",
                "sort_by": "due_date",
                "sort_order": "asc",
                "skip": 0,
                "limit": 20
            }
        }


class ProjectWithTaskCount(ProjectResponse):
    """Project response with task count."""
    task_count: int = 0
