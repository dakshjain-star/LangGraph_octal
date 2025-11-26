"""Comment management routes."""
from fastapi import APIRouter, Depends, status
from typing import List

from app.schemas.comment import (
    CommentResponse,
    CommentCreate,
    CommentUpdate
)
from app.schemas.auth import MessageResponse
from app.controllers.comment_controller import CommentController
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.get(
    "/tasks/{task_id}/comments",
    response_model=List[CommentResponse],
    status_code=status.HTTP_200_OK,
    summary="Get task comments",
    description="Get all comments for a specific task"
)
async def get_task_comments(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all comments for a task.
    
    - **task_id**: The ID of the task
    
    Returns all comments ordered by creation date.
    """
    return await CommentController.get_task_comments(task_id, current_user)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create comment",
    description="Add a new comment to a task"
)
async def create_comment(
    task_id: str,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user)
):
    """
    Create a new comment on a task:
    - **task_id**: The ID of the task to comment on
    - **content**: Comment content (required)
    
    Any authenticated user can comment on tasks.
    """
    return await CommentController.create_comment(task_id, comment_data, current_user)


@router.put(
    "/{comment_id}",
    response_model=CommentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update comment",
    description="Update an existing comment"
)
async def update_comment(
    comment_id: str,
    comment_data: CommentUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update a comment:
    - **comment_id**: The ID of the comment to update
    - **content**: New comment content
    
    Only the comment author and admins can update comments.
    """
    return await CommentController.update_comment(comment_id, comment_data, current_user)


@router.delete(
    "/{comment_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete comment",
    description="Delete a comment"
)
async def delete_comment(
    comment_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a comment:
    - **comment_id**: The ID of the comment to delete
    
    Only the comment author and admins can delete comments.
    """
    return await CommentController.delete_comment(comment_id, current_user)
