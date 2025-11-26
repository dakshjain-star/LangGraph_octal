"""Task management routes."""
from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional

from app.schemas.task import (
    TaskResponse,
    TaskCreate,
    TaskUpdate,
    TaskStatusUpdate,
    TaskAssigneeUpdate,
    TaskStatus,
    TaskPriority,
    TaskWithComments
)
from app.schemas.auth import MessageResponse
from app.controllers.task_controller import TaskController
from app.middleware.auth import get_current_user, require_member_or_admin
from app.models.user import User

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "/",
    response_model=List[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all tasks",
    description="Retrieve list of all tasks with complex filters"
)
async def get_tasks(
    assignee_id: Optional[str] = Query(None),
    creator_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    status_filter: Optional[List[TaskStatus]] = Query(None, alias="status"),
    priority: Optional[List[TaskPriority]] = Query(None),
    search: Optional[str] = Query(None),
    date_filter: str = Query("all"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    Get all tasks with complex filtering and sorting:
    - **assignee_id**: Filter by assignee
    - **creator_id**: Filter by creator
    - **project_id**: Filter by project
    - **status**: Filter by status (To Do, In Progress, Review, Done)
    - **priority**: Filter by priority (Low, Medium, High)
    - **search**: Search in task title and description
    - **date_filter**: Date filter (all, today, this_week, overdue)
    - **sort_by**: Field to sort by (created_at, due_date, priority)
    - **sort_order**: Sort order (asc, desc)
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    
    Requires authentication.
    """
    return await TaskController.get_all_tasks(
        assignee_id=assignee_id,
        creator_id=creator_id,
        project_id=project_id,
        status=status_filter,
        priority=priority,
        search=search,
        date_filter=date_filter,
        sort_by=sort_by,
        sort_order=sort_order,
        skip=skip,
        limit=limit,
        current_user=current_user
    )


@router.get(
    "/my",
    response_model=List[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Get my tasks",
    description="Get tasks assigned to the current user"
)
async def get_my_tasks(
    current_user: User = Depends(get_current_user)
):
    """
    Get all tasks assigned to the current user.
    
    Returns tasks where the current user is the assignee.
    """
    return await TaskController.get_my_tasks(current_user)


@router.get(
    "/created-by-me",
    response_model=List[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Get tasks I created",
    description="Get tasks created by the current user"
)
async def get_tasks_created_by_me(
    current_user: User = Depends(get_current_user)
):
    """
    Get all tasks created by the current user.
    
    Returns tasks where the current user is the creator.
    """
    return await TaskController.get_tasks_created_by_me(current_user)


@router.get(
    "/stats",
    response_model=dict,
    status_code=status.HTTP_200_OK,
    summary="Get task statistics",
    description="Get task statistics for the current user"
)
async def get_task_stats(
    current_user: User = Depends(get_current_user)
):
    """
    Get task statistics including:
    - Total tasks
    - Tasks by status
    - Tasks by priority
    - Overdue tasks
    
    Statistics are scoped to tasks visible to the current user.
    """
    return await TaskController.get_task_stats(current_user)


@router.get(
    "/{task_id}",
    response_model=TaskWithComments,
    status_code=status.HTTP_200_OK,
    summary="Get task by ID",
    description="Retrieve a specific task by its ID with comments"
)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific task by ID including all comments.
    
    - **task_id**: The ID of the task to retrieve
    
    Requires authentication.
    """
    return await TaskController.get_task_by_id(task_id, current_user)


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create task",
    description="Create a new task"
)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(require_member_or_admin)
):
    """
    Create a new task:
    - **title**: Task title (required)
    - **description**: Task description (optional)
    - **status**: Task status (default: To Do)
    - **priority**: Task priority (default: Medium)
    - **due_date**: Task due date (optional)
    - **assignee_id**: User ID to assign the task to (required)
    - **project_id**: Project ID to associate the task with (optional)
    
    Requires Member or Admin role.
    """
    return await TaskController.create_task(task_data, current_user)


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task",
    description="Update task information"
)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update task information:
    - **task_id**: The ID of the task to update
    - **task_data**: Updated task information (all fields optional)
    
    Task creators, assignees, and admins can update tasks.
    """
    return await TaskController.update_task(task_id, task_data, current_user)


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task status",
    description="Update a task's status"
)
async def update_task_status(
    task_id: str,
    status_data: TaskStatusUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update a task's status:
    - **task_id**: The ID of the task to update
    - **status**: New status (To Do, In Progress, Review, Done)
    
    Task assignees, creators, and admins can update status.
    """
    return await TaskController.update_task_status(task_id, status_data, current_user)


@router.patch(
    "/{task_id}/assignee",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task assignee",
    description="Update a task's assignee"
)
async def update_task_assignee(
    task_id: str,
    assignee_data: TaskAssigneeUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update a task's assignee:
    - **task_id**: The ID of the task to update
    - **assignee_id**: New assignee user ID
    
    Task creators and admins can reassign tasks.
    """
    return await TaskController.update_task_assignee(task_id, assignee_data, current_user)


@router.delete(
    "/{task_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete task",
    description="Delete a task"
)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a task:
    - **task_id**: The ID of the task to delete
    
    Task creators and admins can delete tasks.
    This will also delete all associated comments.
    """
    return await TaskController.delete_task(task_id, current_user)
