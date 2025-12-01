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
async def _create_task_async(
    title: str,
    due_date: str,
    assignee_id: str,
    current_user_id: str,
    company_id: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project_id: Optional[str] = None
):
    """Async implementation of create task."""
    from dash_api.app.models.user import User
    from dash_api.app.models.task import Task, TaskStatus, TaskPriority, Collaborator
    from dash_api.app.models.project import Project
    from dash_api.app.models.company import Company
    
    # Find assignee by ID
    assignee = await User.get(assignee_id)
    if not assignee:
        return "Error: Assignee not found. Use 'list users' to see available users."
    
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
    
    # Get project info if provided
    project_name = None
    if project_id:
        project = await Project.get(project_id)
        if project:
            project_name = project.name
    
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
        project_name=project_name
    )
    
    await new_task.insert()
    return f"Task '{title}' created successfully and assigned to {assignee.name}. Task ID: {str(new_task.id)}"


async def _list_users_async(current_user_id: str, company_id: str):
    """Async implementation of list users in the same company."""
    from dash_api.app.models.user import User, UserStatus
    
    # Find users in the same company
    users = await User.find(
        {"$or": [
            {"company_ids": company_id},
            {"company_id": company_id},
            {"current_company_id": company_id}
        ]},
        {"name": 1, "email": 1, "_id": 1, "role": 1, "status": 1, "avatar_url": 1}
    ).to_list()
    
    if not users:
        return "No other users found in your organization."
    
    user_list = []
    for user in users:
        # Skip the current user
        if str(user.id) == current_user_id:
            continue
            
        # Only show active users
        if user.status != UserStatus.ACTIVE:
            continue
            
        name = user.name or "Unknown"
        email = user.email or "N/A"
        role = user.role.value if user.role else "Member"
        user_id = str(user.id)
        
        user_list.append(f"- **{name}** ({email}) - {role} [ID: {user_id}]")
    
    if not user_list:
        return "No other active users found in your organization."
    
    return "**Available Users in Your Company:**\n" + "\n".join(user_list)


async def _view_my_tasks_async(current_user_id: str, company_id: str):
    """Async implementation of view my tasks."""
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
        return "No tasks found."
    
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
            "id": str(t.id),
            "title": t.title,
            "description": t.description or "No description",
            "status": t.status.value if t.status else "To Do",
            "priority": t.priority.value if t.priority else "Medium",
            "due_date": due_date_str,
            "is_overdue": is_overdue,
            "assignee": t.assignee_name or "Unknown",
            "created_by": creator_name,
            "project": t.project_name or "No project"
        })
    
    return json.dumps(task_list)


async def _update_task_status_async(task_id: str, new_status: str, current_user_id: str, company_id: str):
    """Async implementation of update task status."""
    from dash_api.app.models.task import Task, TaskStatus
    
    task = await Task.get(task_id)
    if not task:
        return "Error: Task not found."
    
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


async def _update_task_priority_async(task_id: str, new_priority: str, current_user_id: str, company_id: str):
    """Async implementation of update task priority."""
    from dash_api.app.models.task import Task, TaskPriority
    
    task = await Task.get(task_id)
    if not task:
        return "Error: Task not found."
    
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


async def _delete_task_async(task_id: str, current_user_id: str, company_id: str):
    """Async implementation of delete task."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.comment import Comment
    
    task = await Task.get(task_id)
    if not task:
        return "Error: Task not found."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.creator_id != current_user_id:
        return "Error: Only the task creator can delete this task."
    
    task_title = task.title
    
    # Delete associated comments
    await Comment.find(Comment.task_id == task_id).delete()
    
    # Delete task
    await task.delete()
    
    return f"Task '{task_title}' deleted successfully."


async def _list_projects_async(current_user_id: str, company_id: str):
    """Async implementation of list projects."""
    from dash_api.app.models.project import Project, ProjectStatus
    
    projects = await Project.find(
        {"company_id": company_id, "status": ProjectStatus.ACTIVE}
    ).to_list()
    
    if not projects:
        return "No active projects found in your company."
    
    project_list = []
    for p in projects:
        project_list.append(f"- **{p.name}** (ID: {str(p.id)}) - Client: {p.client_name}")
    
    return "**Active Projects:**\n" + "\n".join(project_list)


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
    assignee_id: str,
    current_user_id: str,
    company_id: str,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    project_id: Optional[str] = None
):
    """Create a new task in the system.
    
    Required fields:
    - title: Task title (required)
    - due_date: Task due date in YYYY-MM-DD format (required)
    - assignee_id: User ID of the person assigned to the task (required) - get from list_users
    - current_user_id: Current logged-in user ID (auto-populated by system)
    - company_id: Current company ID (auto-populated by system)
    
    Optional fields:
    - description: Task description (optional)
    - priority: Task priority - Low, Medium, or High (optional, default: Medium)
    - project_id: Project ID to associate with (optional) - get from list_projects
    """
    return run_async(_create_task_async(
        title, due_date, assignee_id, current_user_id, company_id,
        description, priority, project_id
    ))


@tool
def list_users(current_user_id: str, company_id: str):
    """List all active users in the organization who can be assigned tasks.
    This shows user names, emails, roles, and IDs needed for task assignment.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_list_users_async(current_user_id, company_id))


@tool
def view_my_tasks(current_user_id: str, company_id: str):
    """View all tasks where you are the assignee or creator.
    Shows task details including status, priority, due dates, and assignments.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_view_my_tasks_async(current_user_id, company_id))


@tool
def update_task_status(task_id: str, new_status: str, current_user_id: str, company_id: str):
    """Update the status of a task.
    
    Parameters:
    - task_id: The ID of the task to update (get from view_my_tasks)
    - new_status: New status - "To Do", "In Progress", "Review", or "Done"
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_status_async(task_id, new_status, current_user_id, company_id))


@tool
def update_task_priority(task_id: str, new_priority: str, current_user_id: str, company_id: str):
    """Update the priority of a task.
    
    Parameters:
    - task_id: The ID of the task to update (get from view_my_tasks)
    - new_priority: New priority - "Low", "Medium", or "High"
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_priority_async(task_id, new_priority, current_user_id, company_id))


@tool
def delete_task(task_id: str, current_user_id: str, company_id: str):
    """Delete a task. Only the task creator can delete a task.
    
    Parameters:
    - task_id: The ID of the task to delete (get from view_my_tasks)
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_delete_task_async(task_id, current_user_id, company_id))


@tool
def list_projects(current_user_id: str, company_id: str):
    """List all active projects in the organization.
    Use this to find project IDs when creating tasks.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_list_projects_async(current_user_id, company_id))


@tool
def get_task_stats(current_user_id: str, company_id: str):
    """Get task statistics for the current user.
    Shows counts of tasks by status, priority, and overdue tasks.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_get_task_stats_async(current_user_id, company_id))


# List of all tools for export
tools = [
    create_task,
    list_users,
    view_my_tasks,
    update_task_status,
    update_task_priority,
    delete_task,
    list_projects,
    get_task_stats
]
