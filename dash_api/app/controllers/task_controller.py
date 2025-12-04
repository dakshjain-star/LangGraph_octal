"""Task controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional, Any
import re
from datetime import datetime, timedelta, date as date_type, timezone

from app.models.task import Task, TaskStatus, TaskPriority, Collaborator
from app.models.task_history import TaskHistory, HistoryActionType
from app.models.user import User, UserRole
from app.models.project import Project
from app.models.comment import Comment
from app.models.company import Company
from app.schemas.task import (
    TaskCreate, TaskUpdate, TaskStatusUpdate, TaskAssigneeUpdate,
    TaskResponse, TaskFilter, CollaboratorInfo
)
from app.schemas.task_history import TaskHistoryResponse
from app.services.websocket import (
    notify_task_created, notify_task_updated, 
    notify_task_assigned, notify_task_deleted,
    notify_task_unassigned, notify_task_history_updated,
    notify_task_collaborators_updated
)


# IST timezone offset (UTC+5:30)
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))


def convert_to_ist(dt: datetime) -> str:
    """Convert UTC datetime to IST formatted string."""
    if dt is None:
        return ""
    # Ensure datetime is UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Convert to IST
    ist_dt = dt.astimezone(IST_OFFSET)
    return ist_dt.strftime("%d %b %Y, %I:%M %p IST")


def is_task_overdue(due_date, task_status) -> bool:
    """Check if a task is overdue based on its due_date and status."""
    if not due_date or task_status == TaskStatus.DONE:
        return False
    today = datetime.utcnow().date()
    # Handle both date and datetime types
    if isinstance(due_date, datetime):
        due_date = due_date.date()
    return due_date < today


def build_collaborator_info_list(collaborators: List[Collaborator]) -> List[CollaboratorInfo]:
    """Convert list of Collaborator models to CollaboratorInfo schemas."""
    return [
        CollaboratorInfo(
            user_id=c.user_id,
            user_name=c.user_name,
            user_avatar=c.user_avatar
        )
        for c in (collaborators or [])
    ]


async def create_task_history(
    task_id: str,
    action: HistoryActionType,
    user: User,
    company_id: Optional[str] = None,
    field_name: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None
) -> TaskHistory:
    """Create a task history entry."""
    history = TaskHistory(
        task_id=task_id,
        action=action,
        field_name=field_name,
        old_value=old_value,
        new_value=new_value,
        user_id=str(user.id),
        user_name=user.name,
        user_avatar=user.avatar_url,
        company_id=company_id
    )
    await history.insert()
    
    # Send WebSocket notification for history update
    if company_id:
        history_data = {
            "id": str(history.id),
            "task_id": str(history.task_id),
            "action": history.action,
            "field_name": history.field_name,
            "old_value": history.old_value,
            "new_value": history.new_value,
            "user_name": history.user_name,
            "user_avatar": history.user_avatar,
            "created_at": convert_to_ist(history.created_at)
        }
        await notify_task_history_updated(task_id, history_data, company_id)
    
    return history


async def log_task_changes(
    task_id: str,
    old_task: Dict,
    new_data: Dict,
    user: User,
    company_id: Optional[str] = None
) -> List[TaskHistory]:
    """Log all changes made to a task."""
    history_entries = []
    
    # Field mapping for better action types
    field_action_map = {
        "status": HistoryActionType.STATUS_CHANGED,
        "priority": HistoryActionType.PRIORITY_CHANGED,
        "assignee_id": HistoryActionType.ASSIGNEE_CHANGED,
        "due_date": HistoryActionType.DUE_DATE_CHANGED,
        "project_id": HistoryActionType.PROJECT_CHANGED,
        "title": HistoryActionType.TITLE_CHANGED,
        "description": HistoryActionType.DESCRIPTION_CHANGED,
        "collaborator_ids": HistoryActionType.COLLABORATORS_CHANGED,
    }
    
    for field, new_value in new_data.items():
        if field in old_task:
            old_value = old_task.get(field)
            
            # Normalize values for comparison
            old_compare = old_value
            new_compare = new_value
            
            # Handle special comparisons
            if field == "due_date":
                # Normalize datetime to date strings for comparison
                if old_compare and hasattr(old_compare, 'date'):
                    old_compare = old_compare.date().isoformat()
                elif old_compare and hasattr(old_compare, 'isoformat'):
                    old_compare = old_compare.isoformat()[:10]
                elif old_compare and isinstance(old_compare, str):
                    old_compare = old_compare[:10]
                    
                if new_compare and hasattr(new_compare, 'date'):
                    new_compare = new_compare.date().isoformat()
                elif new_compare and hasattr(new_compare, 'isoformat'):
                    new_compare = new_compare.isoformat()[:10]
                elif new_compare and isinstance(new_compare, str):
                    new_compare = new_compare[:10]
            
            elif field == "collaborator_ids":
                # Normalize lists for comparison - sort them to ignore order
                old_compare = sorted(old_value) if old_value else []
                new_compare = sorted(new_value) if new_value else []
            
            # Skip if values are the same
            if old_compare == new_compare:
                continue  # Skip unchanged fields
            
            action = field_action_map.get(field, HistoryActionType.UPDATED)
            
            # Make human-readable values for certain fields
            display_old = old_value
            display_new = new_value
            
            if field == "assignee_id":
                display_old = old_task.get("assignee_name", old_value)
                # Get new assignee name
                if new_value:
                    new_assignee = await User.get(new_value)
                    display_new = new_assignee.name if new_assignee else new_value
            
            if field == "project_id":
                display_old = old_task.get("project_name") or "None"
                if new_value:
                    new_project = await Project.get(new_value)
                    display_new = new_project.name if new_project else "None"
                else:
                    display_new = "None"
            
            if field == "due_date":
                if old_value:
                    if hasattr(old_value, 'date'):
                        display_old = old_value.date().isoformat()
                    elif hasattr(old_value, 'isoformat'):
                        display_old = old_value.isoformat()[:10]
                    elif isinstance(old_value, str):
                        display_old = old_value[:10]
                    else:
                        display_old = str(old_value)[:10]
                else:
                    display_old = "None"
                if new_value:
                    if hasattr(new_value, 'date'):
                        display_new = new_value.date().isoformat()
                    elif hasattr(new_value, 'isoformat'):
                        display_new = new_value.isoformat()[:10]
                    elif isinstance(new_value, str):
                        display_new = new_value[:10]
                    else:
                        display_new = str(new_value)[:10]
                else:
                    display_new = "None"
            
            if field == "collaborator_ids":
                # Get collaborator names from old_task data
                old_names = old_task.get("collaborator_names", [])
                display_old = ", ".join(old_names) if old_names else "None"
                
                # Get new collaborator names by looking up users
                if new_value:
                    new_names = []
                    for user_id in new_value:
                        user = await User.get(user_id)
                        if user:
                            new_names.append(user.name)
                    display_new = ", ".join(new_names) if new_names else "None"
                else:
                    display_new = "None"
            
            history = await create_task_history(
                task_id=task_id,
                action=action,
                user=user,
                company_id=company_id,
                field_name=field,
                old_value=display_old,
                new_value=display_new
            )
            history_entries.append(history)
    
    return history_entries


async def build_collaborators_from_ids(collaborator_ids: List[str], company_id: str, assignee_id: Optional[str] = None) -> List[Collaborator]:
    """Build list of Collaborator objects from user IDs, validating they're from the same company.
    
    Args:
        collaborator_ids: List of user IDs to add as collaborators
        company_id: Company ID to validate users belong to
        assignee_id: Optional assignee ID to exclude from collaborators (assignee cannot be a collaborator)
    """
    collaborators = []
    for user_id in collaborator_ids:
        # Skip if this user is the assignee
        if assignee_id and user_id == assignee_id:
            continue
            
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Collaborator user {user_id} not found"
            )
        # Verify user belongs to the same company
        user_company_ids = user.get_effective_company_ids()
        if company_id not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Collaborator {user.name} does not belong to the same company"
            )
        collaborators.append(Collaborator(
            user_id=str(user.id),
            user_name=user.name,
            user_avatar=user.avatar_url
        ))
    return collaborators


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
                    collaborators=build_collaborator_info_list(task.collaborators),
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
            collaborators=build_collaborator_info_list(task.collaborators),
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
        
        # Build collaborators list from IDs (excluding assignee)
        collaborators = []
        if data.collaborator_ids:
            collaborators = await build_collaborators_from_ids(data.collaborator_ids, company_id, data.assignee_id)
        
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
            collaborators=collaborators,
            creator_id=str(current_user.id),
            company_id=company_id,
            company_name=company_name,
            project_id=data.project_id,
            project_name=project_name
        )
        
        await task.insert()
        
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
            collaborators=build_collaborator_info_list(task.collaborators),
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
        
        # Store old values for history tracking
        old_task_data = {
            "title": task.title,
            "description": task.description,
            "status": task.status.value if task.status else None,
            "priority": task.priority.value if task.priority else None,
            "due_date": task.due_date,
            "assignee_id": task.assignee_id,
            "assignee_name": task.assignee_name,
            "project_id": task.project_id,
            "project_name": task.project_name,
            "collaborator_ids": [c.user_id for c in (task.collaborators or [])],
            "collaborator_names": [c.user_name for c in (task.collaborators or [])],
        }
        
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
            
            # Remove new assignee from collaborators if they're in the list
            if task.collaborators:
                task.collaborators = [c for c in task.collaborators if c.user_id != task.assignee_id]
        
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
        
        # If collaborator_ids is being changed, rebuild the collaborators list
        if "collaborator_ids" in update_data:
            collaborator_ids = update_data.pop("collaborator_ids")
            if collaborator_ids is not None:
                # Use the updated assignee_id if it's being changed, otherwise use existing
                current_assignee_id = task.assignee_id
                task.collaborators = await build_collaborators_from_ids(collaborator_ids, task.company_id, current_assignee_id)
        
        # Convert date to datetime for Beanie compatibility
        if "due_date" in update_data and update_data["due_date"]:
            if isinstance(update_data["due_date"], date_type) and not isinstance(update_data["due_date"], datetime):
                update_data["due_date"] = datetime.combine(update_data["due_date"], datetime.min.time())
        
        for field, value in update_data.items():
            setattr(task, field, value)
        
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Log changes to history
        new_task_data = data.model_dump(exclude_unset=True)
        # Convert enum values to strings for comparison
        if "status" in new_task_data and new_task_data["status"]:
            new_task_data["status"] = new_task_data["status"].value if hasattr(new_task_data["status"], 'value') else new_task_data["status"]
        if "priority" in new_task_data and new_task_data["priority"]:
            new_task_data["priority"] = new_task_data["priority"].value if hasattr(new_task_data["priority"], 'value') else new_task_data["priority"]
        
        await log_task_changes(
            task_id=str(task.id),
            old_task=old_task_data,
            new_data=new_task_data,
            user=current_user,
            company_id=task.company_id
        )
        
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
            collaborators=build_collaborator_info_list(task.collaborators),
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
        
        # If assignee changed, notify both old and new assignees
        if assignee_changed:
            # Notify old assignee that task was unassigned from them
            if old_assignee_id and old_assignee_id != str(current_user.id):
                await notify_task_unassigned(task_data, old_assignee_id, str(current_user.id))
            
            # Notify new assignee that task was assigned to them
            if task.assignee_id != str(current_user.id):
                await notify_task_assigned(task_data, task.assignee_id, str(current_user.id))
        
        # If collaborators changed, notify about the update
        if "collaborator_ids" in data.model_dump(exclude_unset=True):
            collaborators_info = {
                "task_id": str(task.id),
                "collaborators": [
                    {
                        "user_id": c.user_id,
                        "user_name": c.user_name,
                        "user_avatar": c.user_avatar
                    }
                    for c in (task.collaborators or [])
                ]
            }
            await notify_task_collaborators_updated(str(task.id), collaborators_info, task.company_id, str(current_user.id))
        
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
        
        # Store old status for history
        old_status = task.status.value if task.status else None
        
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
        new_status = data.status
        task.status = new_status
        task.updated_at = datetime.utcnow()
        await task.save()
        
        # Log status change to history
        if old_status != new_status.value:
            await create_task_history(
                task_id=str(task.id),
                action=HistoryActionType.STATUS_CHANGED,
                user=current_user,
                company_id=task.company_id,
                field_name="status",
                old_value=old_status,
                new_value=new_status.value
            )
        
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
            collaborators=build_collaborator_info_list(task.collaborators),
            creator_id=task.creator_id,
            project_id=task.project_id,
            project_name=task.project_name,
            company_id=task.company_id,
            company_name=task.company_name,
            created_at=task.created_at,
            updated_at=task.updated_at,
            is_overdue=is_task_overdue(task.due_date, task.status)
        )

        # Broadcast update so dashboards refresh immediately
        task_data = task_response.model_dump()
        for field in ("due_date", "created_at", "updated_at"):
            if task_data.get(field) and hasattr(task_data[field], "isoformat"):
                task_data[field] = task_data[field].isoformat()

        await notify_task_updated(task_data, task.company_id, str(current_user.id))

        return task_response
    
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
        
        # Store original assignee for notification
        original_assignee_id = task.assignee_id
        
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
            collaborators=build_collaborator_info_list(task.collaborators),
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
        
        # Notify company about task update
        await notify_task_updated(task_data, task.company_id, str(current_user.id))
        
        # Notify old assignee that task was unassigned from them
        if original_assignee_id and original_assignee_id != data.assignee_id and original_assignee_id != str(current_user.id):
            await notify_task_unassigned(task_data, original_assignee_id, str(current_user.id))
        
        # Notify new assignee that task was assigned to them
        if task.assignee_id != str(current_user.id):
            await notify_task_assigned(task_data, task.assignee_id, str(current_user.id))
        
        return task_response
    
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
                    collaborators=build_collaborator_info_list(task.collaborators),
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
                    collaborators=build_collaborator_info_list(task.collaborators),
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
    
    @staticmethod
    async def get_task_history(task_id: str, current_user: User, skip: int = 0, limit: int = 50) -> Dict:
        """Get history for a specific task."""
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
                detail="Not authorized to view this task's history"
            )
        
        # Get total count
        total = await TaskHistory.find(TaskHistory.task_id == task_id).count()
        
        # Get history entries sorted by created_at descending (most recent first)
        history_entries = await TaskHistory.find(
            TaskHistory.task_id == task_id
        ).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()
        
        # Convert to response format with IST timestamps
        history_responses = []
        for entry in history_entries:
            history_responses.append(
                TaskHistoryResponse(
                    id=str(entry.id),
                    task_id=entry.task_id,
                    action=entry.action,
                    field_name=entry.field_name,
                    old_value=entry.old_value,
                    new_value=entry.new_value,
                    user_id=entry.user_id,
                    user_name=entry.user_name,
                    user_avatar=entry.user_avatar,
                    company_id=entry.company_id,
                    created_at=entry.created_at,
                    created_at_ist=convert_to_ist(entry.created_at)
                )
            )
        
        return {
            "history": [h.model_dump() for h in history_responses],
            "total": total
        }
