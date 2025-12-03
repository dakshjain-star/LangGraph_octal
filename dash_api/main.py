"""Main FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import uvicorn
import os

from app.config import settings
from app.database import connect_to_mongo, close_mongo_connection
from app.middleware.error_handler import setup_exception_handlers
from app.routes import (
    auth_router,
    users_router,
    projects_router,
    tasks_router,
    comments_router,
    dashboard_router,
    settings_router,
    invitations_router,
    websocket_router,
    profile_router
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    ## Dash SaaS API
    
    A comprehensive REST API for project and task management.
    
    ### Features
    
    * **Authentication** - JWT-based authentication with refresh tokens
    * **User Management** - User registration, profiles, and role-based access control
    * **Project Management** - Create, update, and organize projects
    * **Task Management** - Advanced task management with filtering and search
    * **Comments** - Task commenting system
    * **Dashboard** - Real-time statistics and analytics
    
    ### Authentication
    
    Most endpoints require authentication. Include the JWT token in the Authorization header:
    
    ```
    Authorization: Bearer <your_access_token>
    ```
    
    ### Roles
    
    * **Admin** - Full access to all resources
    * **Member** - Can create and manage own tasks/projects
    * **Viewer** - Read-only access
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware
cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
cors_headers = ["Content-Type", "Authorization"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_credentials,
    allow_methods=cors_methods,
    allow_headers=cors_headers,
    expose_headers=["Content-Type", "Authorization"],
    max_age=600,
)

# Setup exception handlers
setup_exception_handlers(app)

# Event handlers
@app.on_event("startup")
async def startup_event():
    """Connect to MongoDB on startup."""
    logger.info("Starting up Dash SaaS API...")
    await connect_to_mongo()
    logger.info(f"API running at http://{settings.host}:{settings.port}")
    logger.info(f"Documentation available at http://{settings.host}:{settings.port}/docs")


@app.on_event("shutdown")
async def shutdown_event():
    """Close MongoDB connection on shutdown."""
    logger.info("Shutting down Dash SaaS API...")
    await close_mongo_connection()


# Include routers
app.include_router(auth_router, prefix=f"{settings.api_prefix}/auth", tags=["Authentication"])
app.include_router(users_router, prefix=f"{settings.api_prefix}/users", tags=["Users"])
app.include_router(profile_router, prefix=f"{settings.api_prefix}/profile", tags=["Profile"])
app.include_router(projects_router, prefix=f"{settings.api_prefix}/projects", tags=["Projects"])
app.include_router(tasks_router, prefix=f"{settings.api_prefix}/tasks", tags=["Tasks"])
app.include_router(comments_router, prefix=f"{settings.api_prefix}", tags=["Comments"])
app.include_router(dashboard_router, prefix=f"{settings.api_prefix}/dashboard", tags=["Dashboard"])
app.include_router(settings_router, prefix=f"{settings.api_prefix}/settings", tags=["Settings"])
app.include_router(invitations_router, prefix=f"{settings.api_prefix}/invitations", tags=["Invitations"])
app.include_router(websocket_router, prefix=f"{settings.api_prefix}", tags=["WebSocket"])

# Mount static files for uploaded avatars
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(os.path.join(uploads_dir, "avatars"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": "/docs",
        "redoc": "/redoc",
        "api_prefix": settings.api_prefix
    }


# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "api": "running",
        "database": "connected"
    }


if __name__ == "__main__":
    # Run with uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
