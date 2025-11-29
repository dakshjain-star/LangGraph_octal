"""Task controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional
import re
from datetime import datetime, timedelta, date as date_type

from app.models.task import Task, TaskStatus, TaskPriority
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.comment import Comment
from app.models.company import Company
from app.schemas.task import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, TaskAssigneeUpdate,
    TaskResponse, TaskFilter
)
from app.services.websocket import (
    notify_task_created, notify_task_updated, 
    notify_task_assigned, notify_task_deleted
)


def is_task_overdue(due_date, task_status) -> bool:
    """Check if a task is overdue based on its due_date and status."""
    if not due_date or task_status == TaskStatus.DONE:
        return False
    today = datetime.utcnow().date()
    # Handle both date and datetime types
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    return due_date < today


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
        current_user: User = None,
        all_companies: bool = False
    ) -> List[TaskResponse]:
        """Get all tasks with complex filtering.
        
        Args:
            all_companies: If True, show tasks from all companies user belongs to
        """
        query = {}
        
        # Filter by company - users can see tasks based on all_companies flag
        if current_user:
            if all_companies:
                # Show tasks from all companies user is associated with
                company_ids = current_user.get_effective_company_ids()
                if company_ids:
                    query["company_id"] = {"$in": company_ids}
                else:
                    return []
            else:
                # Default: only show tasks from current effective company
                effective_company_id = current_user.get_effective_company_id()
                if effective_company_id:
                    query["company_id"] = effective_company_id
                else:
                    # If no company, return empty list (shouldn't see any tasks)
                    return []
        
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
            # Use datetime for comparison since due_date is stored as datetime
            today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())
            today_end = datetime.combine(datetime.utcnow().date(), datetime.max.time())
            
            if date_filter == "today":
                query["due_date"] = {"$gte": today_start, "$lte": today_end}
            
            elif date_filter == "this_week":
                # Get start of week (Monday) and end of week (Sunday)
                today = datetime.utcnow().date()
                start_of_week = datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time())
                end_of_week = datetime.combine(today + timedelta(days=6 - today.weekday()), datetime.max.time())
                query["due_date"] = {
                    "$gte": start_of_week,
                    "$lte": end_of_week
                }
            
            elif date_filter == "overdue":
                query["due_date"] = {"$lt": today_start}
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
        
        # Build a cache of company names for tasks missing company_name
        company_ids_needing_names = set()
        for task in tasks:
            if task.company_id and not task.company_name:
                company_ids_needing_names.add(task.company_id)
        
        company_name_cache = {}
        if company_ids_needing_names:
            companies = await Company.find({"_id": {"$in": list(company_ids_needing_names)}}).to_list()
            for company in companies:
                company_name_cache[str(company.id)] = company.name
        
        task_responses = []
        for task in tasks:
            # Get company name from task or look it up
            company_name = task.company_name
            if not company_name and task.company_id:
                company_name = company_name_cache.get(task.company_id)
            
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
                    company_id=task.company_id,
                    company_name=company_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_task_overdue(task.due_date, task.status)
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
        
        # Check company access - allow access from any of user's companies
        user_company_ids = current_user.get_effective_company_ids()
        if task.company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this task"
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
        
        # Look up company name if missing
        company_name = task.company_name
        if not company_name and task.company_id:
            company = await Company.find_one({"_id": task.company_id})
            if company:
                company_name = company.name
        
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
            company_id=task.company_id,
            company_name=company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
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
        
        # Convert date to datetime for Beanie compatibility
        due_date = data.due_date
        if due_date and isinstance(due_date, date_type) and not isinstance(due_date, datetime):
            due_date = datetime.combine(due_date, datetime.min.time())
        
        # Get company name
        company_id = current_user.get_effective_company_id()
        company_name = current_user.current_company_name
        if company_id and not company_name:
            # Look up company name if not available from user
            company = await Company.get(company_id)
            if company:
                company_name = company.name
        
        # Create task
        task = Task(
            title=data.title,
            description=data.description,
            status=data.status,
            priority=data.priority,
            due_date=due_date,
            assignee_id=data.assignee_id,
            assignee_name=assignee.name,
            assignee_avatar=assignee.avatar_url,
            creator_id=str(current_user.id),
            company_id=company_id,
            company_name=company_name,
            project_id=data.project_id,
            project_name=project_name
        )
        
        await task.insert()
        
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
            company_id=task.company_id,
            company_name=current_user.current_company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
        )
        
        # Send WebSocket notifications
        task_data = task_response.model_dump()
        # Convert datetime objects to ISO strings for JSON serialization
        if task_data.get('due_date'):
            task_data['due_date'] = task_data['due_date'].isoformat() if hasattr(task_data['due_date'], 'isoformat') else str(task_data['due_date'])
        if task_data.get('created_at'):
            task_data['created_at'] = task_data['created_at'].isoformat() if hasattr(task_data['created_at'], 'isoformat') else str(task_data['created_at'])
        if task_data.get('updated_at'):
            task_data['updated_at'] = task_data['updated_at'].isoformat() if hasattr(task_data['updated_at'], 'isoformat') else str(task_data['updated_at'])
        
        await notify_task_created(task_data, company_id, str(current_user.id))
        
        # Notify assignee specifically if different from creator
        if data.assignee_id != str(current_user.id):
            await notify_task_assigned(task_data, data.assignee_id, str(current_user.id))
        
        return task_response
    
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
        
        # Store original assignee for notification tracking
        original_assignee_id = task.assignee_id
        
        # Check company access - allow access from any of user's companies
        user_company_ids = current_user.get_effective_company_ids()
        if task.company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this task"
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
        
        # Convert date to datetime for Beanie compatibility
        if "due_date" in update_data and update_data["due_date"]:
            if isinstance(update_data["due_date"], date_type) and not isinstance(update_data["due_date"], datetime):
                update_data["due_date"] = datetime.combine(update_data["due_date"], datetime.min.time())
        
        for field, value in update_data.items():
            setattr(task, field, value)
        
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Track if assignee changed for notification
        assignee_changed = "assignee_id" in data.model_dump(exclude_unset=True)
        old_assignee_id = original_assignee_id if assignee_changed else None
        
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
            company_id=task.company_id,
            company_name=task.company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
        )
        
        # Send WebSocket notifications
        task_data = task_response.model_dump()
        # Convert datetime objects to ISO strings for JSON serialization
        if task_data.get('due_date'):
            task_data['due_date'] = task_data['due_date'].isoformat() if hasattr(task_data['due_date'], 'isoformat') else str(task_data['due_date'])
        if task_data.get('created_at'):
            task_data['created_at'] = task_data['created_at'].isoformat() if hasattr(task_data['created_at'], 'isoformat') else str(task_data['created_at'])
        if task_data.get('updated_at'):
            task_data['updated_at'] = task_data['updated_at'].isoformat() if hasattr(task_data['updated_at'], 'isoformat') else str(task_data['updated_at'])
        
        await notify_task_updated(task_data, task.company_id, str(current_user.id))
        
        # If assignee changed, notify new assignee
        if assignee_changed and task.assignee_id != str(current_user.id):
            await notify_task_assigned(task_data, task.assignee_id, str(current_user.id))
        
        return task_response
    
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
        
        # Check company access - allow access from any of user's companies
        user_company_ids = current_user.get_effective_company_ids()
        if task.company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this task"
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
            company_id=task.company_id,
            company_name=task.company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
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
        
        # Check company access - allow access from any of user's companies
        user_company_ids = current_user.get_effective_company_ids()
        if task.company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this task"
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
            company_id=task.company_id,
            company_name=task.company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
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
        
        # Check company access - allow access from any of user's companies
        user_company_ids = current_user.get_effective_company_ids()
        if task.company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this task"
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
        
        # Store company_id before deletion for notification
        company_id = task.company_id
        
        # Delete task
        await task.delete()
        
        # Send WebSocket notification
        await notify_task_deleted(task_id, company_id, str(current_user.id))
        
        return {"message": "Task deleted successfully"}
    
    @staticmethod
    async def get_my_tasks(current_user: User, limit: int = 10, all_companies: bool = False) -> List[TaskResponse]:
        """Get tasks assigned to me that are not done.
        
        Args:
            all_companies: If True, show tasks from all companies user belongs to
        """
        # Build company filter
        if all_companies:
            company_ids = current_user.get_effective_company_ids()
            company_filter = {"$in": company_ids} if company_ids else None
        else:
            company_filter = current_user.get_effective_company_id()
        
        if not company_filter:
            return []
        
        # Build query
        query = {
            "assignee_id": str(current_user.id),
            "status": {"$ne": TaskStatus.DONE}
        }
        
        if all_companies:
            query["company_id"] = {"$in": current_user.get_effective_company_ids()}
        else:
            query["company_id"] = current_user.get_effective_company_id()
        
        tasks = await Task.find(query).sort([("due_date", 1)]).limit(limit).to_list()
        
        # Build a cache of company names for tasks missing company_name
        company_ids_needing_names = set()
        for task in tasks:
            if task.company_id and not task.company_name:
                company_ids_needing_names.add(task.company_id)
        
        company_name_cache = {}
        if company_ids_needing_names:
            companies = await Company.find({"_id": {"$in": list(company_ids_needing_names)}}).to_list()
            for company in companies:
                company_name_cache[str(company.id)] = company.name
        
        task_responses = []
        for task in tasks:
            # Get company name from task or look it up
            company_name = task.company_name
            if not company_name and task.company_id:
                company_name = company_name_cache.get(task.company_id)
            
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
                    company_id=task.company_id,
                    company_name=company_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_task_overdue(task.due_date, task.status)
                )
            )
        
        return task_responses
    
    @staticmethod
    async def get_tasks_created_by_me(current_user: User, limit: int = 10, all_companies: bool = False) -> List[TaskResponse]:
        """Get tasks created by me.
        
        Args:
            all_companies: If True, show tasks from all companies user belongs to
        """
        # Build query
        query = {"creator_id": str(current_user.id)}
        
        if all_companies:
            company_ids = current_user.get_effective_company_ids()
            if company_ids:
                query["company_id"] = {"$in": company_ids}
            else:
                return []
        else:
            effective_company_id = current_user.get_effective_company_id()
            if effective_company_id:
                query["company_id"] = effective_company_id
            else:
                return []
        
        tasks = await Task.find(query).sort([("created_at", -1)]).limit(limit).to_list()
        
        # Build a cache of company names for tasks missing company_name
        company_ids_needing_names = set()
        for task in tasks:
            if task.company_id and not task.company_name:
                company_ids_needing_names.add(task.company_id)
        
        company_name_cache = {}
        if company_ids_needing_names:
            companies = await Company.find({"_id": {"$in": list(company_ids_needing_names)}}).to_list()
            for company in companies:
                company_name_cache[str(company.id)] = company.name
        
        task_responses = []
        for task in tasks:
            # Get company name from task or look it up
            company_name = task.company_name
            if not company_name and task.company_id:
                company_name = company_name_cache.get(task.company_id)
            
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
                    company_id=task.company_id,
                    company_name=company_name,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    is_overdue=is_task_overdue(task.due_date, task.status)
                )
            )
        
        return task_responses
    
    @staticmethod
    async def get_task_stats(current_user: User, all_companies: bool = False) -> Dict:
        """Get task statistics for dashboard."""
        # Aggregation pipeline for task statistics
        pipeline = [
            {
                "$match": {
                    "company_id": current_user.get_effective_company_id(),
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
            Task.company_id == current_user.get_effective_company_id(),
            Task.status != TaskStatus.DONE
        ).to_list()
        
        overdue_count = sum(1 for task in overdue_tasks if is_task_overdue(task.due_date, task.status))
        
        return {
            "tasks_completed": stats.get("completed", [{}])[0].get("count", 0) if stats.get("completed") else 0,
            "pending_tasks": stats.get("pending", [{}])[0].get("count", 0) if stats.get("pending") else 0,
            "high_priority_tasks": stats.get("high_priority", [{}])[0].get("count", 0) if stats.get("high_priority") else 0,
            "tasks_in_progress": stats.get("in_progress", [{}])[0].get("count", 0) if stats.get("in_progress") else 0,
            "overdue_tasks": overdue_count
        }
