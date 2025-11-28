"""MongoDB database configuration and connection management."""
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager."""
    
    client: Optional[AsyncIOMotorClient] = None
    
    @classmethod
    async def connect_db(cls):
        """Connect to MongoDB and initialize Beanie ODM."""
        try:
            logger.info(f"Connecting to MongoDB at {settings.mongodb_url}")
            
            cls.client = AsyncIOMotorClient(
                settings.mongodb_url,
                minPoolSize=settings.mongodb_min_pool_size,
                maxPoolSize=settings.mongodb_max_pool_size,
                serverSelectionTimeoutMS=5000,
            )
            
            # Get database
            database = cls.client[settings.mongodb_db_name]
            
            # Import models for Beanie initialization
            from app.models.user import User
            from app.models.company import Company
            from app.models.project import Project
            from app.models.task import Task
            from app.models.comment import Comment
            from app.models.invitation import Invitation
            
            # Initialize Beanie with document models
            await init_beanie(
                database=database,
                document_models=[User, Company, Project, Task, Comment, Invitation]
            )
            
            logger.info("Successfully connected to MongoDB and initialized Beanie")
            
            # Create indexes
            await cls.create_indexes()
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    @classmethod
    async def close_db(cls):
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            logger.info("MongoDB connection closed")
    
    @classmethod
    async def create_indexes(cls):
        """Create database indexes for performance optimization."""
        try:
            from app.models.user import User
            from app.models.project import Project
            from app.models.task import Task
            from app.models.comment import Comment
            
            # User indexes
            await User.find_one().motor.create_index("email", unique=True)
            await User.find_one().motor.create_index("status")
            await User.find_one().motor.create_index("role")
            
            # Project indexes
            await Project.find_one().motor.create_index("owner_id")
            await Project.find_one().motor.create_index("status")
            await Project.find_one().motor.create_index("due_date")
            await Project.find_one().motor.create_index("client_name")
            
            # Task indexes
            await Task.find_one().motor.create_index("assignee_id")
            await Task.find_one().motor.create_index("creator_id")
            await Task.find_one().motor.create_index("project_id")
            await Task.find_one().motor.create_index("status")
            await Task.find_one().motor.create_index("priority")
            await Task.find_one().motor.create_index("due_date")
            
            # Comment indexes
            await Comment.find_one().motor.create_index("task_id")
            await Comment.find_one().motor.create_index("user_id")
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.warning(f"Error creating indexes (may already exist): {e}")
    
    @classmethod
    def get_database(cls):
        """Get the database instance."""
        if not cls.client:
            raise Exception("Database not connected. Call connect_db() first.")
        return cls.client[settings.mongodb_db_name]


# Convenience functions
async def connect_to_mongo():
    """Connect to MongoDB."""
    await MongoDB.connect_db()


async def close_mongo_connection():
    """Close MongoDB connection."""
    await MongoDB.close_db()
