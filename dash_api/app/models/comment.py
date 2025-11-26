"""Comment model for MongoDB."""
from beanie import Document
from pydantic import Field
from datetime import datetime


class Comment(Document):
    """Comment document model for MongoDB."""
    
    task_id: str = Field(...)
    user_id: str = Field(...)
    user_name: str = Field(...)  # Denormalized for performance
    content: str = Field(..., min_length=1)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "comments"
        indexes = [
            "task_id",
            "user_id",
            "created_at",
        ]
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task123",
                "user_id": "user456",
                "user_name": "John Doe",
                "content": "Great progress on this task!"
            }
        }
    
    async def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow()
        await self.save()
