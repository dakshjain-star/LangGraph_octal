"""Comment controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List
from datetime import datetime

from app.models.comment import Comment
from app.models.task import Task
from app.models.user import User, UserRole
from app.schemas.comment import (
    CommentCreate, CommentUpdate, CommentResponse
)


class CommentController:
    """Comment controller for handling comment operations."""
    
    @staticmethod
    async def get_task_comments(task_id: str, current_user: User) -> List[CommentResponse]:
        """Get all comments for a task, sorted by created_at."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check company access - user can access if they belong to the task's company
        # Personal tasks (company_id=None) are accessible to their creator/assignee
        user_company_ids = current_user.get_effective_company_ids()
        is_personal_task = task.company_id is None
        has_company_access = task.company_id in user_company_ids if task.company_id else False
        
        if not is_personal_task and not has_company_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task"
            )
        
        # Get comments sorted by creation date
        comments = await Comment.find(Comment.task_id == task_id)\
            .sort([("created_at", 1)])\
            .to_list()
        
        return [
            CommentResponse(
                id=str(comment.id),
                task_id=comment.task_id,
                user_id=comment.user_id,
                user_name=comment.user_name,
                content=comment.content,
                created_at=comment.created_at,
                updated_at=comment.updated_at
            )
            for comment in comments
        ]
    
    @staticmethod
    async def create_comment(task_id: str, data: CommentCreate, current_user: User) -> CommentResponse:
        """Create a new comment on a task."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check company access - user can comment if they belong to the task's company
        # Personal tasks (company_id=None) are accessible to their creator/assignee
        user_company_ids = current_user.get_effective_company_ids()
        is_personal_task = task.company_id is None
        has_company_access = task.company_id in user_company_ids if task.company_id else False
        
        if not is_personal_task and not has_company_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task"
            )
        
        # Create comment
        comment = Comment(
            task_id=task_id,
            user_id=str(current_user.id),
            user_name=current_user.name,
            content=data.content
        )
        
        await comment.insert()
        
        return CommentResponse(
            id=str(comment.id),
            task_id=comment.task_id,
            user_id=comment.user_id,
            user_name=comment.user_name,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at
        )
    
    @staticmethod
    async def update_comment(comment_id: str, data: CommentUpdate, current_user: User) -> CommentResponse:
        """Update a comment."""
        # Check if comment exists
        comment = await Comment.get(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check permissions - only the comment owner can update it
        if comment.user_id != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this comment"
            )
        
        # Update comment
        comment.content = data.content
        comment.updated_at = datetime.utcnow()
        await comment.save()
        
        return CommentResponse(
            id=str(comment.id),
            task_id=comment.task_id,
            user_id=comment.user_id,
            user_name=comment.user_name,
            content=comment.content,
            created_at=comment.created_at,
            updated_at=comment.updated_at
        )
    
    @staticmethod
    async def delete_comment(comment_id: str, current_user: User) -> Dict:
        """Delete a comment."""
        # Check if comment exists
        comment = await Comment.get(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check permissions - owner or admin can delete
        if comment.user_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this comment"
            )
        
        # Delete comment
        await comment.delete()
        
        return {"message": "Comment deleted successfully"}
