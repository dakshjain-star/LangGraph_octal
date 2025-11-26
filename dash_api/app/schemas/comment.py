"""Comment schemas for request and response validation."""
from pydantic import BaseModel, Field
from datetime import datetime


class CommentBase(BaseModel):
    """Base comment schema."""
    content: str = Field(..., min_length=1)


class CommentCreate(CommentBase):
    """Comment creation schema."""
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "Great progress on this task!"
            }
        }


class CommentUpdate(BaseModel):
    """Comment update schema."""
    content: str = Field(..., min_length=1)


class CommentResponse(CommentBase):
    """Comment response schema."""
    id: str
    task_id: str
    user_id: str
    user_name: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "507f1f77bcf86cd799439011",
                "task_id": "507f1f77bcf86cd799439012",
                "user_id": "507f1f77bcf86cd799439013",
                "user_name": "John Doe",
                "content": "Great progress on this task!",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
        }
