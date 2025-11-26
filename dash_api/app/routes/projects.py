"""Project management routes."""
from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional

from app.schemas.project import (
    ProjectResponse,
    ProjectCreate,
    ProjectUpdate,
    ProjectStatusUpdate,
    ProjectStatus
)
from app.schemas.task import TaskResponse
from app.schemas.auth import MessageResponse
from app.controllers.project_controller import ProjectController
from app.middleware.auth import get_current_user, require_member_or_admin
from app.models.user import User

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get(
    "/",
    response_model=List[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all projects",
    description="Retrieve list of all projects with optional filters"
)
async def get_projects(
    status_filter: Optional[List[ProjectStatus]] = Query(None, alias="status"),
    owner_id: Optional[str] = Query(None),
    client_name: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    Get all projects with optional filtering and sorting:
    - **status**: Filter by project status (Active, Archived, On Hold)
    - **owner_id**: Filter by project owner
    - **client_name**: Filter by client name
    - **search**: Search in project name and description
    - **sort_by**: Field to sort by (created_at, due_date)
    - **sort_order**: Sort order (asc, desc)
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    
    Requires authentication.
    """
    return await ProjectController.get_all_projects(
        status=status_filter,
        owner_id=owner_id,
        client_name=client_name,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
        current_user=current_user
    )


@router.get(
    "/owners",
    response_model=List[dict],
    status_code=status.HTTP_200_OK,
    summary="Get project owners",
    description="Get list of unique project owners"
)
async def get_project_owners(
    current_user: User = Depends(get_current_user)
):
    """
    Get a list of unique project owners.
    
    Returns list of users who own at least one project.
    """
    return await ProjectController.get_project_owners(current_user)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project by ID",
    description="Retrieve a specific project by its ID"
)
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific project by ID.
    
    - **project_id**: The ID of the project to retrieve
    
    Requires authentication.
    """
    return await ProjectController.get_project_by_id(project_id, current_user)


@router.get(
    "/{project_id}/tasks",
    response_model=List[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Get project tasks",
    description="Get all tasks for a specific project"
)
async def get_project_tasks(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all tasks associated with a project.
    
    - **project_id**: The ID of the project
    
    Returns all tasks belonging to the project.
    """
    return await ProjectController.get_project_tasks(project_id, current_user)


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create project",
    description="Create a new project"
)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(require_member_or_admin)
):
    """
    Create a new project:
    - **name**: Project name (required)
    - **description**: Project description (required)
    - **client_name**: Client name (required)
    - **due_date**: Project due date (optional)
    - **owner_id**: Project owner ID (required)
    - **status**: Project status (default: Active)
    
    Requires Member or Admin role.
    """
    return await ProjectController.create_project(project_data, current_user)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project",
    description="Update project information"
)
async def update_project(
    project_id: str,
    project_data: ProjectUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update project information:
    - **project_id**: The ID of the project to update
    - **project_data**: Updated project information (all fields optional)
    
    Only project owners and admins can update projects.
    """
    return await ProjectController.update_project(project_id, project_data, current_user)


@router.patch(
    "/{project_id}/status",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project status",
    description="Update a project's status"
)
async def update_project_status(
    project_id: str,
    status_data: ProjectStatusUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update a project's status:
    - **project_id**: The ID of the project to update
    - **status**: New status (Active, Archived, On Hold)
    
    Only project owners and admins can update status.
    """
    return await ProjectController.update_project_status(project_id, status_data, current_user)


@router.delete(
    "/{project_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete project",
    description="Delete a project"
)
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a project:
    - **project_id**: The ID of the project to delete
    
    Only project owners and admins can delete projects.
    This will also delete all associated tasks.
    """
    return await ProjectController.delete_project(project_id, current_user)
