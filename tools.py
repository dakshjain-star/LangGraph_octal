"""
LangGraph Chatbot Tools - Updated for dash_api schema.
Uses async Beanie ODM models matching the dash_saas system.
"""
from langchain_core.tools import tool
from typing import Optional, List
import json
from datetime import datetime, date as date_type
import asyncio
import sys
import os
import threading
import logging

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

logger = logging.getLogger(__name__)

# Store reference to main event loop
_main_loop: Optional[asyncio.AbstractEventLoop] = None

def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop reference (call from FastAPI startup)."""
    global _main_loop
    _main_loop = loop
    logger.info(f"Main event loop set: {loop}")

# --- Async Helper ---
def run_async(coro):
    """Run async code in sync context for LangGraph tools.
    
    This handles running async operations from ThreadPoolExecutor threads
    by scheduling them on the main event loop.
    """
    global _main_loop
    
    # If we have a reference to the main loop and it's running, schedule on it
    if _main_loop is not None and _main_loop.is_running():
        try:
            # Use thread-safe method to run coroutine on the main loop
            future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
            # Use a shorter timeout to catch issues faster
            return future.result(timeout=30)
        except TimeoutError:
            logger.error("Async operation timed out after 30 seconds")
            # Cancel the future if possible
            future.cancel()
            return "Error: Operation timed out. Please try again."
        except Exception as e:
            logger.error(f"Error in run_async: {e}")
            return f"Error: {str(e)}"
    
    # Fallback: try to create a new event loop for this thread
    try:
        loop = asyncio.get_running_loop()
        # We're in a thread with a running loop - schedule on it
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    except RuntimeError:
        # No running loop in this thread - create a new one
        try:
            # Create a new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            logger.error(f"Error creating new event loop: {e}")
            return f"Error: {str(e)}"


# --- Async Database Operations ---
async def _find_task_by_title_async(title_query: str, current_user_id: str, company_id: str):
    """Find a task by title (partial match) in the company."""
    from dash_api.app.models.task import Task
    
    # Find all tasks in the company
    tasks = await Task.find({"company_id": company_id}).to_list()
    
    title_lower = title_query.lower().strip()
    matching_tasks = []
    
    for task in tasks:
        task_title = (task.title or "").lower()
        # Exact match first, then partial match
        if title_lower == task_title:
            return task  # Exact match - return immediately
        if title_lower in task_title or task_title in title_lower:
            matching_tasks.append(task)
    
    if matching_tasks:
        # Return the first match
        return matching_tasks[0]
    return None


async def _find_project_by_name_async(name_query: str, company_id: str):
    """Find a project by name (partial match) in the company."""
    from dash_api.app.models.project import Project, ProjectStatus
    
    projects = await Project.find(
        {"company_id": company_id, "status": ProjectStatus.ACTIVE}
    ).to_list()
    
    name_lower = name_query.lower().strip()
    matching_projects = []
    
    for project in projects:
        project_name = (project.name or "").lower()
        if name_lower == project_name:
            return project  # Exact match
        if name_lower in project_name or project_name in name_lower:
            matching_projects.append(project)
    
    if matching_projects:
        return matching_projects[0]
    return None


async def _create_task_async(
    title: str,
    due_date: str,
    assignee_name: str,
    current_user_id: str,
    company_id: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project_name: Optional[str] = None
):
    """Async implementation of create task."""
    from dash_api.app.models.user import User
    from dash_api.app.models.task import Task, TaskStatus, TaskPriority, Collaborator
    from dash_api.app.models.project import Project
    from dash_api.app.models.company import Company
    
    # Find assignee by name
    found_user = await _find_user_by_name_async(assignee_name, current_user_id, company_id)
    if not found_user:
        users_list = await _list_users_async(current_user_id, company_id)
        return f"Error: Could not find a user named '{assignee_name}' in your company.\n\nHere are the available users:\n{users_list}"
    
    assignee_id = found_user["id"]
    assignee = await User.get(assignee_id)
    if not assignee:
        return "Error: Assignee not found."
    
    # Check if user is trying to assign task to themselves
    if assignee_id == current_user_id:
        return "Error: You cannot assign a task to yourself. Please assign it to another user."
    
    # Verify assignee is in the same company
    assignee_company_ids = assignee.get_effective_company_ids()
    if company_id not in assignee_company_ids:
        return "Error: The assignee is not a member of your current company."
    
    # Get current user for creator info
    creator = await User.get(current_user_id)
    if not creator:
        return "Error: Current user not found."
    
    # Get project info if provided by name
    project_id = None
    actual_project_name = None
    if project_name:
        project = await _find_project_by_name_async(project_name, company_id)
        if project:
            project_id = str(project.id)
            actual_project_name = project.name
        else:
            projects_list = await _list_projects_async(current_user_id, company_id)
            return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Get company name
    company = await Company.get(company_id)
    company_name = company.name if company else None
    
    # Parse due date
    try:
        parsed_date = datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        return "Error: Invalid date format. Use YYYY-MM-DD format."
    
    # Map priority string to enum
    priority_map = {
        "low": TaskPriority.LOW,
        "medium": TaskPriority.MEDIUM,
        "high": TaskPriority.HIGH
    }
    task_priority = priority_map.get((priority or "medium").lower(), TaskPriority.MEDIUM)
    
    # Create task
    new_task = Task(
        title=title,
        description=description or "",
        status=TaskStatus.TODO,
        priority=task_priority,
        due_date=parsed_date,
        assignee_id=assignee_id,
        assignee_name=assignee.name,
        assignee_avatar=assignee.avatar_url,
        collaborators=[],
        creator_id=current_user_id,
        company_id=company_id,
        company_name=company_name,
        project_id=project_id,
        project_name=actual_project_name
    )
    
    await new_task.insert()
    return f"Task '{title}' created successfully and assigned to {assignee.name}."


async def _list_users_async(current_user_id: str, company_id: str):
    """Async implementation of list users in the same company."""
    from dash_api.app.models.user import User, UserStatus
    
    # Find users in the same company - use broader query
    users = await User.find({}).to_list()
    
    if not users:
        return "No users found in the database."
    
    user_list = []
    for user in users:
        # Check if user belongs to this company
        user_company_ids = user.get_effective_company_ids() if hasattr(user, 'get_effective_company_ids') else []
        user_current_company = getattr(user, 'current_company_id', None) or getattr(user, 'company_id', None)
        
        # Check company membership
        in_company = (
            company_id in user_company_ids or 
            user_current_company == company_id or
            (hasattr(user, 'company_ids') and company_id in (user.company_ids or []))
        )
        
        if not in_company:
            continue
        
        # Skip the current user
        if str(user.id) == current_user_id:
            continue
            
        # Only show active users
        if hasattr(user, 'status') and user.status != UserStatus.ACTIVE:
            continue
            
        name = user.name or "Unknown"
        email = user.email or "N/A"
        role = user.role.value if hasattr(user, 'role') and user.role else "Member"
        
        user_list.append(f"- **{name}** ({email}) - {role}")
    
    if not user_list:
        return "No other active users found in your organization."
    
    return "**Available Users in Your Company:**\n" + "\n".join(user_list)


async def _find_user_by_name_async(name_query: str, current_user_id: str, company_id: str):
    """Find a user by name (partial match) in the same company."""
    from dash_api.app.models.user import User, UserStatus
    import re
    
    # Find all users and filter
    users = await User.find({}).to_list()
    
    matching_users = []
    name_lower = name_query.lower().strip()
    
    for user in users:
        # Check if user belongs to this company
        user_company_ids = user.get_effective_company_ids() if hasattr(user, 'get_effective_company_ids') else []
        user_current_company = getattr(user, 'current_company_id', None) or getattr(user, 'company_id', None)
        
        in_company = (
            company_id in user_company_ids or 
            user_current_company == company_id or
            (hasattr(user, 'company_ids') and company_id in (user.company_ids or []))
        )
        
        if not in_company:
            continue
        
        # Check if name matches (case-insensitive partial match)
        user_name = (user.name or "").lower()
        if name_lower in user_name or user_name in name_lower:
            matching_users.append({
                "id": str(user.id),
                "name": user.name,
                "email": user.email,
                "role": user.role.value if hasattr(user, 'role') and user.role else "Member"
            })
    
    if not matching_users:
        return None
    
    # Return the best match (exact match first, then first partial)
    for u in matching_users:
        if u["name"].lower() == name_lower:
            return u
    
    return matching_users[0]


async def _view_my_tasks_async(current_user_id: str, company_id: str):
    """Async implementation of view my tasks - tasks assigned to the current user."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.user import User
    
    # Find tasks where user is ASSIGNEE (assigned to me)
    tasks = await Task.find({
        "company_id": company_id,
        "assignee_id": current_user_id
    }).sort([("due_date", 1)]).to_list()
    
    if not tasks:
        return "No tasks assigned to you."
    
    task_list = []
    for t in tasks:
        # Get creator name
        creator = await User.get(t.creator_id)
        creator_name = creator.name if creator else "Unknown"
        
        # Format due date
        due_date_str = "Not set"
        if t.due_date:
            if isinstance(t.due_date, datetime):
                due_date_str = t.due_date.strftime("%Y-%m-%d")
            else:
                due_date_str = str(t.due_date)
        
        # Check if overdue
        is_overdue = False
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type):
                is_overdue = due < datetime.utcnow().date()
        
        task_list.append({
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "collaborators": [c.user_name for c in t.collaborators] if t.collaborators else [],
            "created_by": creator_name,
            "project": t.project_name or "No project"
        })
    
    return json.dumps(task_list)


async def _view_all_my_tasks_async(current_user_id: str, company_id: str):
    """Async implementation of view all tasks related to current user (assigned to or created by)."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.user import User
    
    # Find tasks where user is assignee or creator
    tasks = await Task.find({
        "$and": [
            {"company_id": company_id},
            {"$or": [
                {"assignee_id": current_user_id},
                {"creator_id": current_user_id}
            ]}
        ]
    }).sort([("due_date", 1)]).to_list()
    
    if not tasks:
        return "No tasks found related to you."
    
    # Separate tasks into assigned and created
    assigned_tasks = []
    created_tasks = []
    
    for t in tasks:
        # Get creator name
        creator = await User.get(t.creator_id)
        creator_name = creator.name if creator else "Unknown"
        
        # Format due date
        due_date_str = "Not set"
        if t.due_date:
            if isinstance(t.due_date, datetime):
                due_date_str = t.due_date.strftime("%Y-%m-%d")
            else:
                due_date_str = str(t.due_date)
        
        # Check if overdue
        is_overdue = False
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type):
                is_overdue = due < datetime.utcnow().date()
        
        task_data = {
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "collaborators": [c.user_name for c in t.collaborators] if t.collaborators else [],
            "created_by": creator_name,
            "project": t.project_name or "No project"
        }
        
        # Categorize the task
        if t.assignee_id == current_user_id:
            assigned_tasks.append(task_data)
        else:
            created_tasks.append(task_data)
    
    return json.dumps({
        "assigned_to_you": assigned_tasks,
        "created_by_you": created_tasks,
        "total_assigned": len(assigned_tasks),
        "total_created": len(created_tasks)
    })


async def _view_tasks_by_user_name_async(user_name: str, current_user_id: str, company_id: str):
    """Async implementation of view tasks by searching user name (admin only)."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.user import User, UserRole
    
    # Check if current user is admin
    current_user = await User.get(current_user_id)
    if not current_user or current_user.role != UserRole.ADMIN:
        return "Error: Only admins can view tasks assigned to other users. Use 'view_my_tasks' to see your own tasks."
    
    # Find user by name
    found_user = await _find_user_by_name_async(user_name, current_user_id, company_id)
    if not found_user:
        # List all users to help
        users_list = await _list_users_async(current_user_id, company_id)
        return f"Error: Could not find a user named '{user_name}' in your company.\n\nHere are the available users:\n{users_list}"
    
    target_user_id = found_user["id"]
    target_user_name = found_user["name"]
    
    # Find tasks assigned to target user
    tasks = await Task.find({
        "company_id": company_id,
        "assignee_id": target_user_id
    }).sort([("due_date", 1)]).to_list()
    
    if not tasks:
        return f"No tasks found assigned to {target_user_name}."
    
    task_list = []
    for t in tasks:
        # Get creator name
        creator = await User.get(t.creator_id)
        creator_name = creator.name if creator else "Unknown"
        
        # Format due date
        due_date_str = "Not set"
        if t.due_date:
            if isinstance(t.due_date, datetime):
                due_date_str = t.due_date.strftime("%Y-%m-%d")
            else:
                due_date_str = str(t.due_date)
        
        # Check if overdue
        is_overdue = False
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type):
                is_overdue = due < datetime.utcnow().date()
        
        task_list.append({
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "collaborators": [c.user_name for c in t.collaborators] if t.collaborators else [],
            "created_by": creator_name,
            "project": t.project_name or "No project"
        })
    
    return json.dumps({"user_name": target_user_name, "tasks": task_list})


async def _view_tasks_by_user_async(target_user_id: str, current_user_id: str, company_id: str):
    """Async implementation of view tasks assigned to a specific user (admin only)."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.user import User, UserRole
    
    # Check if current user is admin
    current_user = await User.get(current_user_id)
    if not current_user or current_user.role != UserRole.ADMIN:
        return "Error: Only admins can view tasks assigned to other users. Use 'view_my_tasks' to see your own tasks."
    
    # Get target user info
    target_user = await User.get(target_user_id)
    if not target_user:
        return "Error: User not found. Use 'list_users' to see available users."
    
    # Verify target user is in the same company
    target_company_ids = target_user.get_effective_company_ids()
    if company_id not in target_company_ids:
        return "Error: User is not a member of your company."
    
    # Find tasks assigned to target user
    tasks = await Task.find({
        "company_id": company_id,
        "assignee_id": target_user_id
    }).sort([("due_date", 1)]).to_list()
    
    if not tasks:
        return f"No tasks found assigned to {target_user.name}."
    
    task_list = []
    for t in tasks:
        # Get creator name
        creator = await User.get(t.creator_id)
        creator_name = creator.name if creator else "Unknown"
        
        # Format due date
        due_date_str = "Not set"
        if t.due_date:
            if isinstance(t.due_date, datetime):
                due_date_str = t.due_date.strftime("%Y-%m-%d")
            else:
                due_date_str = str(t.due_date)
        
        # Check if overdue
        is_overdue = False
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type):
                is_overdue = due < datetime.utcnow().date()
        
        task_list.append({
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "collaborators": [c.user_name for c in t.collaborators] if t.collaborators else [],
            "created_by": creator_name,
            "project": t.project_name or "No project"
        })
    
    return json.dumps({"user_name": target_user.name, "tasks": task_list})


async def _view_all_company_tasks_async(current_user_id: str, company_id: str, filter_by: str = None):
    """Async implementation of view all tasks in the company (admin only)."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.user import User, UserRole
    
    # Check if current user is admin
    current_user = await User.get(current_user_id)
    if not current_user or current_user.role != UserRole.ADMIN:
        return "Error: Only admins can view all company tasks. Use 'view_my_tasks' to see your own tasks."
    
    # Build query
    query = {"company_id": company_id}
    
    # Optional status filter
    if filter_by:
        status_map = {
            "todo": TaskStatus.TODO,
            "to do": TaskStatus.TODO,
            "in progress": TaskStatus.IN_PROGRESS,
            "inprogress": TaskStatus.IN_PROGRESS,
            "review": TaskStatus.REVIEW,
            "done": TaskStatus.DONE,
            "completed": TaskStatus.DONE
        }
        if filter_by.lower() in status_map:
            query["status"] = status_map[filter_by.lower()]
    
    # Find all tasks in company
    tasks = await Task.find(query).sort([("due_date", 1)]).to_list()
    
    if not tasks:
        return "No tasks found in the company."
    
    task_list = []
    for t in tasks:
        # Get creator name
        creator = await User.get(t.creator_id)
        creator_name = creator.name if creator else "Unknown"
        
        # Format due date
        due_date_str = "Not set"
        if t.due_date:
            if isinstance(t.due_date, datetime):
                due_date_str = t.due_date.strftime("%Y-%m-%d")
            else:
                due_date_str = str(t.due_date)
        
        # Check if overdue
        is_overdue = False
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type):
                is_overdue = due < datetime.utcnow().date()
        
        task_list.append({
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "collaborators": [c.user_name for c in t.collaborators] if t.collaborators else [],
            "created_by": creator_name,
            "project": t.project_name or "No project"
        })
    
    return json.dumps({"total_tasks": len(task_list), "tasks": task_list})


async def _update_task_status_async(task_title: str, new_status: str, current_user_id: str, company_id: str):
    """Async implementation of update task status by task title."""
    from dash_api.app.models.task import Task, TaskStatus
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.assignee_id != current_user_id and task.creator_id != current_user_id:
        return "Error: You don't have permission to update this task."
    
    # Map status string to enum
    status_map = {
        "to do": TaskStatus.TODO,
        "todo": TaskStatus.TODO,
        "in progress": TaskStatus.IN_PROGRESS,
        "inprogress": TaskStatus.IN_PROGRESS,
        "in-progress": TaskStatus.IN_PROGRESS,
        "review": TaskStatus.REVIEW,
        "done": TaskStatus.DONE,
        "completed": TaskStatus.DONE
    }
    
    mapped_status = status_map.get(new_status.lower())
    if not mapped_status:
        return f"Error: Invalid status '{new_status}'. Valid options: To Do, In Progress, Review, Done"
    
    task.status = mapped_status
    task.updated_at = datetime.utcnow()
    await task.save()
    
    return f"Task '{task.title}' status updated to '{mapped_status.value}'."


async def _update_task_priority_async(task_title: str, new_priority: str, current_user_id: str, company_id: str):
    """Async implementation of update task priority by task title."""
    from dash_api.app.models.task import Task, TaskPriority
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.assignee_id != current_user_id and task.creator_id != current_user_id:
        return "Error: You don't have permission to update this task."
    
    # Map priority string to enum
    priority_map = {
        "low": TaskPriority.LOW,
        "medium": TaskPriority.MEDIUM,
        "high": TaskPriority.HIGH
    }
    
    mapped_priority = priority_map.get(new_priority.lower())
    if not mapped_priority:
        return f"Error: Invalid priority '{new_priority}'. Valid options: Low, Medium, High"
    
    task.priority = mapped_priority
    task.updated_at = datetime.utcnow()
    await task.save()
    
    return f"Task '{task.title}' priority updated to '{mapped_priority.value}'."


async def _update_task_project_async(task_title: str, project_name: str, current_user_id: str, company_id: str):
    """Async implementation of update task project by task title."""
    from dash_api.app.models.task import Task
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.assignee_id != current_user_id and task.creator_id != current_user_id:
        return "Error: You don't have permission to update this task."
    
    # Handle removing project (if project_name is empty or "none")
    if not project_name or project_name.lower() in ["none", "no project", "remove", "unlink"]:
        old_project = task.project_name or "No project"
        task.project_id = None
        task.project_name = None
        task.updated_at = datetime.utcnow()
        await task.save()
        return f"Task '{task.title}' has been unlinked from project '{old_project}'."
    
    # Find the project by name
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    old_project = task.project_name or "No project"
    task.project_id = str(project.id)
    task.project_name = project.name
    task.updated_at = datetime.utcnow()
    await task.save()
    
    if old_project == "No project":
        return f"Task '{task.title}' has been linked to project '{project.name}'."
    else:
        return f"Task '{task.title}' project changed from '{old_project}' to '{project.name}'."


async def _delete_task_async(task_title: str, current_user_id: str, company_id: str):
    """Async implementation of delete task by task title."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.comment import Comment
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.creator_id != current_user_id:
        return "Error: Only the task creator can delete this task."
    
    actual_task_title = task.title
    task_id = str(task.id)
    
    # Delete associated comments
    await Comment.find(Comment.task_id == task_id).delete()
    
    # Delete task
    await task.delete()
    
    return f"Task '{actual_task_title}' deleted successfully."


async def _list_projects_async(current_user_id: str, company_id: str):
    """Async implementation of list projects."""
    from dash_api.app.models.project import Project, ProjectStatus
    
    # Get all projects in the company (not just active ones)
    projects = await Project.find(
        {"company_id": company_id}
    ).to_list()
    
    if not projects:
        return "No projects found in your company."
    
    project_list = []
    for p in projects:
        status = p.status.value if p.status else "Active"
        project_list.append(f"- **{p.name}** - Client: {p.client_name} (Status: {status})")
    
    return "**All Projects:**\n" + "\n".join(project_list)


async def _get_project_info_async(project_name: str, current_user_id: str, company_id: str):
    """Async implementation of get project info by name."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.task import Task
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Get tasks associated with this project
    project_id = str(project.id)
    tasks = await Task.find({"project_id": project_id, "company_id": company_id}).to_list()
    
    task_count = len(tasks)
    
    return json.dumps({
        "name": project.name,
        "client": project.client_name,
        "status": project.status.value if project.status else "Active",
        "task_count": task_count
    })


async def _get_task_stats_async(current_user_id: str, company_id: str):
    """Async implementation of get task statistics."""
    from dash_api.app.models.task import Task, TaskStatus, TaskPriority
    
    # Get all user's tasks
    tasks = await Task.find({
        "company_id": company_id,
        "$or": [
            {"assignee_id": current_user_id},
            {"creator_id": current_user_id}
        ]
    }).to_list()
    
    # Calculate statistics
    total = len(tasks)
    completed = sum(1 for t in tasks if t.status == TaskStatus.DONE)
    in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
    todo = sum(1 for t in tasks if t.status == TaskStatus.TODO)
    review = sum(1 for t in tasks if t.status == TaskStatus.REVIEW)
    high_priority = sum(1 for t in tasks if t.priority == TaskPriority.HIGH and t.status != TaskStatus.DONE)
    
    # Overdue tasks
    today = datetime.utcnow().date()
    overdue = 0
    for t in tasks:
        if t.due_date and t.status != TaskStatus.DONE:
            due = t.due_date.date() if isinstance(t.due_date, datetime) else t.due_date
            if isinstance(due, date_type) and due < today:
                overdue += 1
    
    return json.dumps({
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "todo": todo,
        "in_review": review,
        "high_priority_pending": high_priority,
        "overdue": overdue
    })


# --- LangGraph Tools (Sync Wrappers) ---

@tool
def create_task(
    title: str,
    due_date: str,
    assignee_name: str,
    current_user_id: str,
    company_id: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project_name: Optional[str] = None
):
    """Create a new task in the system.
    
    Required fields:
    - title: Task title (required)
    - due_date: Task due date in YYYY-MM-DD format (required)
    - assignee_name: Name of the person to assign the task to (required) - e.g., "John", "Samriddhi"
    - current_user_id: Current logged-in user ID (auto-populated by system)
    - company_id: Current company ID (auto-populated by system)
    
    Optional fields:
    - description: Task description (optional)
    - priority: Task priority - Low, Medium, or High (optional, default: Medium)
    - project_name: Name of the project to associate with (optional) - e.g., "Gemini", "Alpha"
    """
    return run_async(_create_task_async(
        title, due_date, assignee_name, current_user_id, company_id,
        description, priority, project_name
    ))


@tool
def list_users(current_user_id: str, company_id: str):
    """List all active users in the organization who can be assigned tasks.
    This shows user names, emails, and roles.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_list_users_async(current_user_id, company_id))


@tool
def view_my_tasks(current_user_id: str, company_id: str):
    """View all tasks assigned to you (where you are the assignee).
    Shows task details including status, priority, due dates, and who created the task.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_view_my_tasks_async(current_user_id, company_id))


@tool
def view_all_my_tasks(current_user_id: str, company_id: str):
    """View ALL tasks related to you - both tasks assigned to you AND tasks created by you.
    Use this when asked about "all tasks" or "my work" to get a complete picture.
    Shows tasks grouped by whether they're assigned to you or created by you.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_view_all_my_tasks_async(current_user_id, company_id))


@tool
def update_task_status(task_title: str, new_status: str, current_user_id: str, company_id: str):
    """Update the status of a task by its title/name.
    
    Parameters:
    - task_title: The title/name of the task to update (e.g., "Major API Integration", "Fix bug")
    - new_status: New status - "To Do", "In Progress", "Review", or "Done"
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_status_async(task_title, new_status, current_user_id, company_id))


@tool
def update_task_priority(task_title: str, new_priority: str, current_user_id: str, company_id: str):
    """Update the priority of a task by its title/name.
    
    Parameters:
    - task_title: The title/name of the task to update (e.g., "Major API Integration", "Fix bug")
    - new_priority: New priority - "Low", "Medium", or "High"
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_priority_async(task_title, new_priority, current_user_id, company_id))


@tool
def delete_task(task_title: str, current_user_id: str, company_id: str):
    """Delete a task by its title/name. Only the task creator can delete a task.
    
    Parameters:
    - task_title: The title/name of the task to delete (e.g., "Major API Integration", "Fix bug")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_delete_task_async(task_title, current_user_id, company_id))


@tool
def update_task_project(task_title: str, project_name: str, current_user_id: str, company_id: str):
    """Update or change the project associated with a task.
    Use this to link a task to a different project, or remove it from a project.
    
    Parameters:
    - task_title: The title/name of the task to update (e.g., "Major API Integration", "Fix bug")
    - project_name: The name of the project to link to (e.g., "Gemini", "Alpha"). Use "none" or "remove" to unlink from current project.
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_project_async(task_title, project_name, current_user_id, company_id))


@tool
def list_projects(current_user_id: str, company_id: str):
    """List all projects in the organization (including all statuses like Active, On Hold, Completed, etc.).
    Use this to find project names when creating tasks or to see all company projects.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_list_projects_async(current_user_id, company_id))


@tool
def get_project_info(project_name: str, current_user_id: str, company_id: str):
    """Get detailed information about a specific project by its name.
    
    Parameters:
    - project_name: The name of the project (e.g., "Gemini", "Alpha")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_project_info_async(project_name, current_user_id, company_id))


@tool
def get_task_stats(current_user_id: str, company_id: str):
    """Get task statistics for the current user.
    Shows counts of tasks by status, priority, and overdue tasks.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_task_stats_async(current_user_id, company_id))


@tool
def view_user_tasks(target_user_name: str, current_user_id: str, company_id: str):
    """View tasks assigned to a specific user in your company by their NAME. ADMIN ONLY.
    Use this when you know the user's name.
    
    Parameters:
    - target_user_name: The name of the user whose tasks you want to view (e.g., "Rohan", "Samriddhi")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_view_tasks_by_user_name_async(target_user_name, current_user_id, company_id))


@tool
def search_user_tasks(user_name: str, current_user_id: str, company_id: str):
    """View tasks assigned to a user by searching their NAME. ADMIN ONLY.
    Use this when you know the user's name but not their ID.
    This is the PREFERRED tool when someone asks "show tasks assigned to [Name]".
    
    Parameters:
    - user_name: The name of the user to search for (e.g., "Samriddhi", "John", etc.)
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_view_tasks_by_user_name_async(user_name, current_user_id, company_id))


@tool
def view_all_company_tasks(current_user_id: str, company_id: str, status_filter: Optional[str] = None):
    """View ALL tasks in the entire company. ADMIN ONLY.
    Use this when you want to see all tasks across all team members.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    - status_filter: Optional filter by status - "To Do", "In Progress", "Review", or "Done"
    """
    return run_async(_view_all_company_tasks_async(current_user_id, company_id, status_filter))


async def _get_task_collaborators_async(task_title: str, current_user_id: str, company_id: str):
    """Async implementation of get task collaborators."""
    from dash_api.app.models.task import Task
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found."
    
    # Get assignee info
    result = f"📋 **Task: {task.title}**\n\n"
    result += f"👤 **Primary Assignee:** {task.assignee_name}\n\n"
    
    # Get collaborators
    if task.collaborators and len(task.collaborators) > 0:
        result += f"🤝 **Collaborators ({len(task.collaborators)}):**\n"
        for collab in task.collaborators:
            result += f"  • {collab.user_name}\n"
    else:
        result += "🤝 **Collaborators:** None\n"
    
    return result


async def _get_task_history_async(task_title: str, current_user_id: str, company_id: str):
    """Async implementation of get task history."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.task_history import TaskHistory
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found."
    
    task_id = str(task.id)
    
    # Get task history (latest 10 entries)
    history = await TaskHistory.find(
        {"task_id": task_id, "company_id": company_id}
    ).sort([("created_at", -1)]).limit(10).to_list()
    
    if not history:
        return f"📋 **{task.title}**\n\n📜 **History:** No changes recorded yet."
    
    result = f"📋 **{task.title}**\n\n📜 **Activity History (Latest 10):**\n\n"
    
    for entry in history:
        timestamp = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else "Unknown"
        action = entry.action.value if hasattr(entry.action, 'value') else str(entry.action)
        
        action_icon = "📝"
        if "status" in action.lower():
            action_icon = "🔄"
        elif "priority" in action.lower():
            action_icon = "🎯"
        elif "assigned" in action.lower():
            action_icon = "👤"
        elif "created" in action.lower():
            action_icon = "✨"
        
        result += f"{action_icon} **{action}** by {entry.user_name}\n"
        result += f"   📅 {timestamp}\n"
        
        if entry.field_name and entry.old_value is not None and entry.new_value is not None:
            result += f"   Changed {entry.field_name}: {entry.old_value} → {entry.new_value}\n"
        
        result += "\n"
    
    return result


async def _get_task_comments_async(task_title: str, current_user_id: str, company_id: str):
    """Async implementation of get task comments (latest 5)."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.comment import Comment
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found."
    
    task_id = str(task.id)
    
    # Get latest 5 comments
    comments = await Comment.find(
        {"task_id": task_id}
    ).sort([("created_at", -1)]).limit(5).to_list()
    
    result = f"📋 **{task.title}**\n\n"
    
    if not comments:
        result += "💬 **Comments:** No comments yet.\n"
        return result
    
    result += f"💬 **Comments (Latest 5):**\n\n"
    
    # Reverse to show chronologically (oldest first)
    comments.reverse()
    
    for comment in comments:
        timestamp = comment.created_at.strftime("%Y-%m-%d %H:%M") if comment.created_at else "Unknown"
        result += f"👤 **{comment.user_name}** - {timestamp}\n"
        result += f"   {comment.content}\n\n"
    
    return result


@tool
def get_task_collaborators(task_title: str, current_user_id: str, company_id: str):
    """Get all collaborators on a specific task.
    Shows the primary assignee and all team members collaborating on this task.
    
    Parameters:
    - task_title: The title/name of the task
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_task_collaborators_async(task_title, current_user_id, company_id))


@tool
def get_task_history(task_title: str, current_user_id: str, company_id: str):
    """Get the activity history of a task - shows what changed and when.
    Displays the latest 10 changes including status updates, priority changes, assignee changes, etc.
    
    Parameters:
    - task_title: The title/name of the task
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_task_history_async(task_title, current_user_id, company_id))


@tool
def get_task_comments(task_title: str, current_user_id: str, company_id: str):
    """Get the latest comments on a task (up to 5 most recent).
    Use this to see what team members have said about the task.
    
    Parameters:
    - task_title: The title/name of the task
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_task_comments_async(task_title, current_user_id, company_id))


# List of all tools for export
tools = [
    create_task,
    list_users,
    view_my_tasks,
    view_all_my_tasks,
    view_user_tasks,
    search_user_tasks,
    view_all_company_tasks,
    update_task_status,
    update_task_priority,
    update_task_project,
    delete_task,
    list_projects,
    get_project_info,
    get_task_stats,
    get_task_collaborators,
    get_task_history,
    get_task_comments
]
