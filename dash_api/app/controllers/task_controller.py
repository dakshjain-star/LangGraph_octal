"""Task controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional
import re
from datetime import datetime, timedelta

from app.models.task import Task, TaskStatus, TaskPriority
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.comment import Comment
from app.schemas.task import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, TaskAssigneeUpdate,
    TaskResponse, TaskFilter
)


class TaskController:
    """Task controller for handling task operations."""
    
    @staticmethod
    async def get_all_tasks(
        assignee_id: Optional[str] = None,
        creator_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[List[TaskStatus]] = None,
        priority: Optional[List[TaskPriority]] = None,
        search: Optional[str] = None,
        date_filter: str = "all",
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
        current_user: User = None
    ) -> List[TaskResponse]:
        """Get all tasks with complex filtering."""
        query = {}
        
        # Apply filters
        if status:
            query["status"] = {"$in": status}
        
        if priority:
            query["priority"] = {"$in": priority}
        
        if assignee_id:
            query["assignee_id"] = assignee_id
        
        if creator_id:
            query["creator_id"] = creator_id
        
        if project_id:
            query["project_id"] = project_id
        
        if search:
            # Search in title and description
            search_regex = re.compile(re.escape(search), re.IGNORECASE)
            query["$or"] = [
                {"title": search_regex},
                {"description": search_regex}
            ]
        
        # Handle date filters
        if date_filter and date_filter != "all":
            today = datetime.utcnow().date()
            
            if date_filter == "today":
                query["due_date"] = today
            
            elif date_filter == "this_week":
                # Get start of week (Monday) and end of week (Sunday)
                start_of_week = today - timedelta(days=today.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                query["due_date"] = {
                    "$gte": start_of_week,
                    "$lte": end_of_week
                }
            
            elif date_filter == "overdue":
                query["due_date"] = {"$lt": today}
                query["status"] = {"$ne": TaskStatus.DONE}
        
        # Get total count
        total = await Task.find(query).count()
        
        # Determine sort order
        sort_direction = 1 if sort_order == "asc" else -1
        
        # Get tasks with pagination and sorting
        tasks = await Task.find(query)\
            .sort((sort_by, sort_direction))\
            .skip(skip)\
            .limit(limit)\
            .to_list()
        
        # Check for overdue tasks
        today = datetime.utcnow().date()
        task_responses = []
        for task in tasks:
            is_overdue = False
            if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
                is_overdue = True
            
            task_responses.append(
                TaskResponse(
                    id=str(task.id),
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    priority=task.priority,
                    due_date=task.due_date,
                    assignee_id=task.assignee_id,
                    assignee_name=task.assignee_name,
                    assignee_avatar=task.assignee_avatar,
                    creator_id=task.creator_id,
                    project_id=task.project_id,
                    project_name=task.project_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_overdue
                )
            )
        
        return task_responses
    
    @staticmethod
    async def get_task_by_id(task_id: str, current_user: User) -> Dict:
        """Get a single task by ID with comments."""
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Get comments for this task
        comments = await Comment.find(Comment.task_id == str(task.id))\
            .sort([("created_at", 1)])\
            .to_list()
        
        comment_list = [
            {
                "id": str(comment.id),
                "task_id": comment.task_id,
                "user_id": comment.user_id,
                "user_name": comment.user_name,
                "content": comment.content,
                "created_at": comment.created_at,
                "updated_at": comment.updated_at
            }
            for comment in comments
        ]
        
        # Check if overdue
        today = datetime.utcnow().date()
        is_overdue = False
        if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
            is_overdue = True
        
        task_response = TaskResponse(
            id=str(task.id),
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            assignee_avatar=task.assignee_avatar,
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue
        )
        
        return {
            **task_response.model_dump(),
            "comments": comment_list
        }
    
    @staticmethod
    async def create_task(data: TaskCreate, current_user: User) -> TaskResponse:
        """Create a new task."""
        # Get assignee information
        assignee = await User.get(data.assignee_id)
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee user not found"
            )
        
        # Get project information if project_id is provided
        project_name = None
        if data.project_id:
            project = await Project.get(data.project_id)
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Project not found"
                )
            project_name = project.name
        
        # Create task
        task = Task(
            title=data.title,
            description=data.description,
            status=data.status,
            priority=data.priority,
            due_date=data.due_date,
            assignee_id=data.assignee_id,
            assignee_name=assignee.name,
            assignee_avatar=assignee.avatar_url,
            creator_id=str(current_user.id),
            project_id=data.project_id,
            project_name=project_name
        )
        
        await task.insert()
        
        # Check if overdue
        today = datetime.utcnow().date()
        is_overdue = False
        if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
            is_overdue = True
        
        return TaskResponse(
            id=str(task.id),
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            assignee_avatar=task.assignee_avatar,
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue
        )
    
    @staticmethod
    async def update_task(task_id: str, data: TaskUpdate, current_user: User) -> TaskResponse:
        """Update task information."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check permissions - creator, assignee, or admin can update
        if (task.creator_id != str(current_user.id) and 
            task.assignee_id != str(current_user.id) and 
            current_user.role != UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this task"
            )
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        
        # If assignee_id is being changed, update assignee_name and assignee_avatar too
        if "assignee_id" in update_data and update_data["assignee_id"]:
            assignee = await User.get(update_data["assignee_id"])
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignee user not found"
                )
            task.assignee_id = update_data["assignee_id"]
            task.assignee_name = assignee.name
            task.assignee_avatar = assignee.avatar_url
            update_data.pop("assignee_id")
        
        # If project_id is being changed, update project_name too
        if "project_id" in update_data:
            if update_data["project_id"]:
                project = await Project.get(update_data["project_id"])
                if not project:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Project not found"
                    )
                task.project_id = update_data["project_id"]
                task.project_name = project.name
            else:
                task.project_id = None
                task.project_name = None
            update_data.pop("project_id")
        
        for field, value in update_data.items():
            setattr(task, field, value)
        
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Check if overdue
        today = datetime.utcnow().date()
        is_overdue = False
        if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
            is_overdue = True
        
        return TaskResponse(
            id=str(task.id),
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            assignee_avatar=task.assignee_avatar,
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue
        )
    
    @staticmethod
    async def update_task_status(task_id: str, data: TaskStatusUpdate, current_user: User) -> TaskResponse:
        """Update task status."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check permissions - creator, assignee, or admin can update
        if (task.creator_id != str(current_user.id) and 
            task.assignee_id != str(current_user.id) and 
            current_user.role != UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this task"
            )
        
        # Update status
        task.status = data.status
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Check if overdue
        today = datetime.utcnow().date()
        is_overdue = False
        if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
            is_overdue = True
        
        return TaskResponse(
            id=str(task.id),
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            assignee_avatar=task.assignee_avatar,
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue
        )
    
    @staticmethod
    async def update_task_assignee(task_id: str, data: TaskAssigneeUpdate, current_user: User) -> TaskResponse:
        """Update task assignee."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check permissions - creator or admin can reassign
        if task.creator_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to reassign this task"
            )
        
        # Get new assignee information
        assignee = await User.get(data.assignee_id)
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee user not found"
            )
        
        # Update assignee
        task.assignee_id = data.assignee_id
        task.assignee_name = assignee.name
        task.assignee_avatar = assignee.avatar_url
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Check if overdue
        today = datetime.utcnow().date()
        is_overdue = False
        if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
            is_overdue = True
        
        return TaskResponse(
            id=str(task.id),
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            assignee_name=task.assignee_name,
            assignee_avatar=task.assignee_avatar,
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_overdue
        )
    
    @staticmethod
    async def delete_task(task_id: str, current_user: User) -> Dict:
        """Delete a task."""
        # Check if task exists
        task = await Task.get(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found"
            )
        
        # Check permissions - creator, assignee, or admin can delete
        if (task.creator_id != str(current_user.id) and 
            task.assignee_id != str(current_user.id) and 
            current_user.role != UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this task"
            )
        
        # Delete associated comments
        comments = await Comment.find(Comment.task_id == str(task.id)).to_list()
        for comment in comments:
            await comment.delete()
        
        # Delete task
        await task.delete()
        
        return {"message": "Task deleted successfully"}
    
    @staticmethod
    async def get_my_tasks(current_user: User, limit: int = 10) -> List[TaskResponse]:
        """Get tasks assigned to me that are not done."""
        tasks = await Task.find(
            Task.assignee_id == str(current_user.id),
            Task.status != TaskStatus.DONE
        ).sort([("due_date", 1)]).limit(limit).to_list()
        
        # Check for overdue tasks
        today = datetime.utcnow().date()
        task_responses = []
        for task in tasks:
            is_overdue = False
            if task.due_date and task.due_date < today:
                is_overdue = True
            
            task_responses.append(
                TaskResponse(
                    id=str(task.id),
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    priority=task.priority,
                    due_date=task.due_date,
                    assignee_id=task.assignee_id,
                    assignee_name=task.assignee_name,
                    assignee_avatar=task.assignee_avatar,
                    creator_id=task.creator_id,
                    project_id=task.project_id,
                    project_name=task.project_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_overdue
                )
            )
        
        return task_responses
    
    @staticmethod
    async def get_tasks_created_by_me(current_user: User, limit: int = 10) -> List[TaskResponse]:
        """Get tasks created by me."""
        tasks = await Task.find(
            Task.creator_id == str(current_user.id)
        ).sort([("created_at", -1)]).limit(limit).to_list()
        
        # Check for overdue tasks
        today = datetime.utcnow().date()
        task_responses = []
        for task in tasks:
            is_overdue = False
            if task.due_date and task.due_date < today and task.status != TaskStatus.DONE:
                is_overdue = True
            
            task_responses.append(
                TaskResponse(
                    id=str(task.id),
                    title=task.title,
                    description=task.description,
                    status=task.status,
                    priority=task.priority,
                    due_date=task.due_date,
                    assignee_id=task.assignee_id,
                    assignee_name=task.assignee_name,
                    assignee_avatar=task.assignee_avatar,
                    creator_id=task.creator_id,
                    project_id=task.project_id,
                    project_name=task.project_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_overdue
                )
            )
        
        return task_responses
    
    @staticmethod
    async def get_task_stats(current_user: User) -> Dict:
        """Get task statistics for dashboard."""
        today = datetime.utcnow().date()
        
        # Aggregation pipeline for task statistics
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"assignee_id": str(current_user.id)},
                        {"creator_id": str(current_user.id)}
                    ]
                }
            },
            {
                "$facet": {
                    "completed": [
                        {"$match": {"status": TaskStatus.DONE}},
                        {"$count": "count"}
                    ],
                    "pending": [
                        {
                            "$match": {
                                "assignee_id": str(current_user.id),
                                "status": {"$ne": TaskStatus.DONE}
                            }
                        },
                        {"$count": "count"}
                    ],
                    "high_priority": [
                        {
                            "$match": {
                                "assignee_id": str(current_user.id),
                                "priority": TaskPriority.HIGH,
                                "status": {"$ne": TaskStatus.DONE}
                            }
                        },
                        {"$count": "count"}
                    ],
                    "in_progress": [
                        {
                            "$match": {
                                "assignee_id": str(current_user.id),
                                "status": TaskStatus.IN_PROGRESS
                            }
                        },
                        {"$count": "count"}
                    ]
                }
            }
        ]
        
        result = await Task.aggregate(pipeline).to_list()
        stats = result[0] if result else {}
        
        # Count overdue tasks manually (can't compare dates easily in aggregation)
        overdue_tasks = await Task.find(
            Task.assignee_id == str(current_user.id),
            Task.status != TaskStatus.DONE
        ).to_list()
        
        overdue_count = sum(1 for task in overdue_tasks if task.due_date and task.due_date < today)
        
        return {
            "tasks_completed": stats.get("completed", [{}])[0].get("count", 0) if stats.get("completed") else 0,
            "pending_tasks": stats.get("pending", [{}])[0].get("count", 0) if stats.get("pending") else 0,
            "high_priority_tasks": stats.get("high_priority", [{}])[0].get("count", 0) if stats.get("high_priority") else 0,
            "tasks_in_progress": stats.get("in_progress", [{}])[0].get("count", 0) if stats.get("in_progress") else 0,
            "overdue_tasks": overdue_count
        }
