"""Dashboard routes for analytics and statistics."""
from fastapi import APIRouter, Depends, status
from typing import List

from app.schemas.dashboard import DashboardStats
from app.schemas.project import ProjectResponse
from app.schemas.task import TaskResponse
from app.controllers.dashboard_controller import DashboardController
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/stats",
    response_model=DashboardStats,
    status_code=status.HTTP_200_OK,
    summary="Get dashboard statistics",
    description="Get comprehensive dashboard statistics for the current user"
)
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get dashboard statistics including:
    - Tasks completed
    - Pending tasks
    - High priority tasks
    - Active projects
    - Overdue tasks
    - Tasks in progress
    
    Statistics are personalized based on the current user.
    """
    return await DashboardController.get_dashboard_stats(current_user)


@router.get(
    "/recent-projects",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="Get recent projects",
    description="Get recently updated projects"
)
async def get_recent_projects(
    current_user: User = Depends(get_current_user)
):
    """
    Get recently updated projects.
    
    Returns the most recently updated projects, sorted by update date.
    """
    return await DashboardController.get_recent_projects(current_user)


@router.get(
    "/my-tasks",
    response_model=List[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Get my pending tasks",
    description="Get pending tasks assigned to the current user"
)
async def get_my_pending_tasks(
    current_user: User = Depends(get_current_user)
):
    """
    Get pending tasks assigned to the current user.
    
    Returns tasks with status "To Do" or "In Progress".
    """
    return await DashboardController.get_my_pending_tasks(current_user)
