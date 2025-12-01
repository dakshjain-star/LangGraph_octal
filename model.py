"""
Database models and connection for the LangGraph Chatbot.
Uses the same Beanie ODM models as dash_api for consistency.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Optional
import logging
import sys
import os

# Add dash_api to path for importing models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

logger = logging.getLogger(__name__)

# --- Database Configuration ---
MONGODB_URI = "mongodb+srv://octaldaksh:octal123@cluster0.5xt6n.mongodb.net/"
MONGODB_DB_NAME = "dash_saas"

# Global client reference
_client: Optional[AsyncIOMotorClient] = None


async def connect_db():
    """Connect to MongoDB and initialize Beanie ODM."""
    global _client
    
    try:
        logger.info(f"Connecting to MongoDB...")
        
        _client = AsyncIOMotorClient(
            MONGODB_URI,
            minPoolSize=5,
            maxPoolSize=20,
            serverSelectionTimeoutMS=5000,
        )
        
        # Get database
        database = _client[MONGODB_DB_NAME]
        
        # Import models from dash_api
        from dash_api.app.models.user import User
        from dash_api.app.models.company import Company
        from dash_api.app.models.project import Project
        from dash_api.app.models.task import Task
        from dash_api.app.models.comment import Comment
        
        # Initialize Beanie with document models
        await init_beanie(
            database=database,
            document_models=[User, Company, Project, Task, Comment]
        )
        
        logger.info("Successfully connected to MongoDB and initialized Beanie")
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def close_db():
    """Close MongoDB connection."""
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_database():
    """Get the database instance."""
    global _client
    if not _client:
        raise Exception("Database not connected. Call connect_db() first.")
    return _client[MONGODB_DB_NAME]


# Re-export models for convenience
# These will be imported after Beanie is initialized
def get_models():
    """Get all Beanie models after initialization."""
    from dash_api.app.models.user import User, UserRole, UserStatus
    from dash_api.app.models.company import Company
    from dash_api.app.models.project import Project, ProjectStatus
    from dash_api.app.models.task import Task, TaskStatus, TaskPriority, Collaborator
    from dash_api.app.models.comment import Comment
    
    return {
        'User': User,
        'UserRole': UserRole,
        'UserStatus': UserStatus,
        'Company': Company,
        'Project': Project,
        'ProjectStatus': ProjectStatus,
        'Task': Task,
        'TaskStatus': TaskStatus,
        'TaskPriority': TaskPriority,
        'Collaborator': Collaborator,
        'Comment': Comment
    }
