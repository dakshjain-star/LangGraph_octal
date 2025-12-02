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
import httpx

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

logger = logging.getLogger(__name__)

# Store reference to main event loop
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# dash_api base URL (where WebSocket connections are managed)
DASH_API_BASE_URL = os.environ.get("DASH_API_URL", "http://localhost:8000")

def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop reference (call from FastAPI startup)."""
    global _main_loop
    _main_loop = loop
    logger.info(f"Main event loop set: {loop}")

# --- WebSocket Notification Helper ---
async def _notify_chatbot_db_change(company_id: str, change_type: str, details: dict = None):
    """Send WebSocket notification when chatbot makes a DB change.
    
    This makes an HTTP request to the dash_api server (port 8000) to trigger
    the WebSocket broadcast. This is necessary because the chatbot runs on
    a separate process (port 8080) and doesn't share the WebSocket connection
    manager with dash_api.
    """
    try:
        logger.info(f"[CHATBOT TOOLS] Attempting to notify via HTTP: {change_type} for company {company_id}")
        logger.info(f"[CHATBOT TOOLS] Details: {details}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DASH_API_BASE_URL}/api/v1/ws/chatbot-notify",
                json={
                    "company_id": company_id,
                    "change_type": change_type,
                    "details": details or {}
                },
                headers={
                    "X-Internal-Secret": "chatbot-internal-secret",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[CHATBOT TOOLS] ✓ Successfully sent notification: {change_type}")
                logger.info(f"[CHATBOT TOOLS] ✓ Users notified: {result.get('users_notified', 0)}")
            else:
                logger.error(f"[CHATBOT TOOLS] ✗ HTTP notification failed: {response.status_code} - {response.text}")
                
    except httpx.ConnectError as e:
        logger.error(f"[CHATBOT TOOLS] ✗ Cannot connect to dash_api at {DASH_API_BASE_URL}: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[CHATBOT TOOLS] ✗ Failed to send notification: {e}")
        logger.error(f"[CHATBOT TOOLS] Traceback: {traceback.format_exc()}")


async def _notify_invitation_to_user(invitee_user_id: str, invitation_data: dict):
    """Send WebSocket notification directly to a specific user when they receive an invitation.
    
    This makes an HTTP request to the dash_api server (port 8000) to trigger
    a USER_INVITED WebSocket event to the specific user.
    """
    try:
        logger.info(f"[CHATBOT TOOLS] Sending invitation notification to user: {invitee_user_id}")
        logger.info(f"[CHATBOT TOOLS] Invitation data: {invitation_data}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DASH_API_BASE_URL}/api/v1/ws/invitation-notify",
                json={
                    "invitee_user_id": invitee_user_id,
                    "invitation_data": invitation_data
                },
                headers={
                    "X-Internal-Secret": "chatbot-internal-secret",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[CHATBOT TOOLS] ✓ Invitation notification sent to user: {invitee_user_id}")
                logger.info(f"[CHATBOT TOOLS] ✓ User online: {result.get('user_online', False)}")
            else:
                logger.error(f"[CHATBOT TOOLS] ✗ Invitation notification failed: {response.status_code} - {response.text}")
                
    except httpx.ConnectError as e:
        logger.error(f"[CHATBOT TOOLS] ✗ Cannot connect to dash_api at {DASH_API_BASE_URL}: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[CHATBOT TOOLS] ✗ Failed to send invitation notification: {e}")
        logger.error(f"[CHATBOT TOOLS] Traceback: {traceback.format_exc()}")

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
            # Log full traceback for debugging
            import traceback
            logger.error(f"Error in run_async (main loop): {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
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
            import traceback
            logger.error(f"Error creating new event loop: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error: {str(e)}"


# --- Async Database Operations ---
async def _find_task_by_title_async(title_query: str, current_user_id: str, company_id: str):
    """Find a task by title (partial match) in the company.
    
    Search priority:
    1. Exact match (case-insensitive)
    2. Title contains the query
    3. Query contains the title
    4. Word-based partial match
    """
    from dash_api.app.models.task import Task
    import logging
    logger = logging.getLogger(__name__)
    
    # Clean the search query
    title_query = title_query.strip()
    if not title_query:
        return None
    
    # Find all tasks in the company
    tasks = await Task.find({"company_id": company_id}).to_list()
    
    if not tasks:
        logger.warning(f"No tasks found for company_id: {company_id}")
        return None
    
    title_lower = title_query.lower()
    
    # First pass: exact match (case-insensitive)
    for task in tasks:
        task_title = (task.title or "").lower().strip()
        if title_lower == task_title:
            logger.info(f"Found exact match: {task.title}")
            return task
    
    # Second pass: title contains the query OR query contains the title
    matching_tasks = []
    for task in tasks:
        task_title = (task.title or "").lower().strip()
        if title_lower in task_title or task_title in title_lower:
            matching_tasks.append((task, len(task_title)))  # Store with length for sorting
    
    if matching_tasks:
        # Sort by title length (prefer shorter/more specific matches)
        matching_tasks.sort(key=lambda x: x[1])
        logger.info(f"Found partial match: {matching_tasks[0][0].title}")
        return matching_tasks[0][0]
    
    # Third pass: word-based matching (any word from query matches)
    query_words = set(title_lower.split())
    for task in tasks:
        task_title = (task.title or "").lower().strip()
        task_words = set(task_title.split())
        # If any significant word matches (longer than 2 chars)
        common_words = query_words & task_words
        significant_matches = [w for w in common_words if len(w) > 2]
        if significant_matches:
            logger.info(f"Found word match: {task.title} (matched words: {significant_matches})")
            return task
    
    logger.warning(f"No task found matching: {title_query}")
    return None


async def _find_project_by_name_async(name_query: str, company_id: str):
    """Find a project by name (partial match) in the company.
    Searches all projects regardless of status (Active, Archived, On Hold).
    """
    from dash_api.app.models.project import Project
    
    # Get ALL projects in the company (not just active)
    projects = await Project.find(
        {"company_id": company_id}
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
    
    # Create history entry for task creation
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    history = TaskHistory(
        task_id=str(new_task.id),
        action=HistoryActionType.CREATED,
        field_name=None,
        old_value=None,
        new_value=title,
        user_id=current_user_id,
        user_name=creator.name,
        user_avatar=creator.avatar_url,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket that chatbot created a task
    await _notify_chatbot_db_change(
        company_id,
        "task_created",
        {"task_id": str(new_task.id), "task_title": title, "assignee": assignee.name}
    )
    
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
    
    # Store old status for history
    old_status = task.status.value if task.status else "To Do"
    
    task.status = mapped_status
    task.updated_at = datetime.utcnow()
    await task.save()
    
    # Create history entry for status change
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    from dash_api.app.models.user import User
    current_user = await User.get(current_user_id)
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.STATUS_CHANGED,
        field_name="status",
        old_value=old_status,
        new_value=mapped_status.value,
        user_id=current_user_id,
        user_name=current_user.name if current_user else "Unknown",
        user_avatar=current_user.avatar_url if current_user else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket that chatbot updated task status
    await _notify_chatbot_db_change(
        company_id,
        "task_status_updated",
        {"task_id": str(task.id), "task_title": task.title, "old_status": old_status, "new_status": mapped_status.value}
    )
    
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
    
    # Store old priority for history
    old_priority = task.priority.value if task.priority else "Medium"
    
    task.priority = mapped_priority
    task.updated_at = datetime.utcnow()
    await task.save()
    
    # Create history entry for priority change
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    from dash_api.app.models.user import User
    current_user = await User.get(current_user_id)
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.PRIORITY_CHANGED,
        field_name="priority",
        old_value=old_priority,
        new_value=mapped_priority.value,
        user_id=current_user_id,
        user_name=current_user.name if current_user else "Unknown",
        user_avatar=current_user.avatar_url if current_user else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket that chatbot updated task priority
    await _notify_chatbot_db_change(
        company_id,
        "task_priority_updated",
        {"task_id": str(task.id), "task_title": task.title, "old_priority": old_priority, "new_priority": mapped_priority.value}
    )
    
    return f"Task '{task.title}' priority updated to '{mapped_priority.value}'."


async def _update_task_due_date_async(task_title: str, new_due_date: str, current_user_id: str, company_id: str):
    """Async implementation of update task due date by task title."""
    from dash_api.app.models.task import Task
    
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if task.assignee_id != current_user_id and task.creator_id != current_user_id:
        return "Error: You don't have permission to update this task."
    
    # Parse the new due date
    try:
        # Support multiple date formats
        parsed_date = None
        for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"]:
            try:
                parsed_date = datetime.strptime(new_due_date, fmt)
                break
            except ValueError:
                continue
        
        if not parsed_date:
            return f"Error: Invalid date format '{new_due_date}'. Please use YYYY-MM-DD format (e.g., 2024-12-31)."
    except Exception as e:
        return f"Error: Could not parse date '{new_due_date}'. Please use YYYY-MM-DD format."
    
    # Store old due date for history
    old_due_date = None
    if task.due_date:
        if isinstance(task.due_date, datetime):
            old_due_date = task.due_date.strftime("%Y-%m-%d")
        else:
            old_due_date = str(task.due_date)
    else:
        old_due_date = "Not set"
    
    task.due_date = parsed_date
    task.updated_at = datetime.utcnow()
    await task.save()
    
    # Create history entry for due date change
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    from dash_api.app.models.user import User
    current_user = await User.get(current_user_id)
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.UPDATED,
        field_name="due_date",
        old_value=old_due_date,
        new_value=parsed_date.strftime("%Y-%m-%d"),
        user_id=current_user_id,
        user_name=current_user.name if current_user else "Unknown",
        user_avatar=current_user.avatar_url if current_user else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket that chatbot updated task due date
    await _notify_chatbot_db_change(
        company_id,
        "task_due_date_updated",
        {"task_id": str(task.id), "task_title": task.title, "old_due_date": old_due_date, "new_due_date": parsed_date.strftime("%Y-%m-%d")}
    )
    
    return f"Task '{task.title}' due date updated to '{parsed_date.strftime('%Y-%m-%d')}'."


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
        
        # Create history entry for project removal
        from dash_api.app.models.task_history import TaskHistory, HistoryActionType
        from dash_api.app.models.user import User
        current_user = await User.get(current_user_id)
        history = TaskHistory(
            task_id=str(task.id),
            action=HistoryActionType.PROJECT_CHANGED,
            field_name="project",
            old_value=old_project,
            new_value="None",
            user_id=current_user_id,
            user_name=current_user.name if current_user else "Unknown",
            user_avatar=current_user.avatar_url if current_user else None,
            company_id=company_id
        )
        await history.insert()
        
        # Notify via WebSocket that chatbot unlinked task from project
        await _notify_chatbot_db_change(
            company_id,
            "task_project_updated",
            {"task_id": str(task.id), "task_title": task.title, "action": "unlinked", "old_project": old_project}
        )
        
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
    
    # Create history entry for project change
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    from dash_api.app.models.user import User
    current_user = await User.get(current_user_id)
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.PROJECT_CHANGED,
        field_name="project",
        old_value=old_project,
        new_value=project.name,
        user_id=current_user_id,
        user_name=current_user.name if current_user else "Unknown",
        user_avatar=current_user.avatar_url if current_user else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket that chatbot updated task project
    await _notify_chatbot_db_change(
        company_id,
        "task_project_updated",
        {"task_id": str(task.id), "task_title": task.title, "old_project": old_project, "new_project": project.name}
    )
    
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
    
    # Delete associated comments - using dictionary-style query for Beanie compatibility
    await Comment.find({"task_id": task_id}).delete()
    
    # Delete task
    await task.delete()
    
    # Notify via WebSocket that chatbot deleted a task
    await _notify_chatbot_db_change(
        company_id,
        "task_deleted",
        {"task_id": task_id, "task_title": actual_task_title}
    )
    
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
def update_task_due_date(task_title: str, new_due_date: str, current_user_id: str, company_id: str):
    """Update the due date/deadline of a task by its title/name.
    
    Parameters:
    - task_title: The title/name of the task to update (e.g., "Major API Integration", "Fix bug")
    - new_due_date: New due date in YYYY-MM-DD format (e.g., "2024-12-31", "2025-01-15")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    """
    return run_async(_update_task_due_date_async(task_title, new_due_date, current_user_id, company_id))


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


async def _get_task_history_async(task_title: str, current_user_id: str, company_id: str, skip: int = 0, limit: int = 50):
    """Async implementation of get task history by task title.
    
    Searches for task by title (case-insensitive, partial match supported).
    """
    from dash_api.app.models.task import Task
    from dash_api.app.models.task_history import TaskHistory
    
    # Clean the input title
    search_title = task_title.strip()
    if not search_title:
        return "Error: Please provide a task title to search for."
    
    # Find task by title using the robust title search
    task = await _find_task_by_title_async(search_title, current_user_id, company_id)
    
    if not task:
        # If not found, try a more aggressive search - list all tasks and show suggestions
        all_tasks = await Task.find({"company_id": company_id}).to_list()
        if all_tasks:
            suggestions = []
            search_lower = search_title.lower()
            for t in all_tasks[:10]:  # Show up to 10 suggestions
                title = t.title or ""
                # Check for any word match
                if any(word in title.lower() for word in search_lower.split()):
                    suggestions.append(f"- {title}")
            
            if suggestions:
                return f"Error: Task '{search_title}' not found.\n\n**Did you mean one of these?**\n" + "\n".join(suggestions)
        
        return f"Error: Task '{search_title}' not found. Please check the task name and try again."
    
    # Verify the task belongs to user's company
    if task.company_id != company_id:
        return f"Error: Task not found in your company."
    
    # Get the task_id as string - this is critical for the query
    task_id = str(task.id)
    
    # Debug: Log what we're searching for
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Searching history for task_id: {task_id}, task title: {task.title}")
    
    # Get history from database - using direct dict query for reliability
    history = await TaskHistory.find(
        {"task_id": task_id}
    ).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()
    
    # If no history with string ID, try with the raw task.id
    if not history:
        history = await TaskHistory.find(
            {"task_id": task.id}
        ).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()
    
    if not history:
        return f"📋 **{task.title}**\n\n📜 **History:** No changes recorded yet.\n\n💡 **Tip:** History is created when task properties are changed (status, priority, assignee, etc.)."
    
    result = f"📋 **{task.title}**\n\n📜 **Activity History ({len(history)} entries):**\n\n"
    
    for entry in history:
        # Format timestamp - prefer IST formatted timestamp if available
        if hasattr(entry, 'created_at_ist') and entry.created_at_ist:
            timestamp = entry.created_at_ist
        elif entry.created_at:
            timestamp = entry.created_at.strftime("%Y-%m-%d %H:%M UTC")
        else:
            timestamp = "Unknown"
        
        action = entry.action.value if hasattr(entry.action, 'value') else str(entry.action)
        
        # Action icons based on type
        action_icon = "📝"
        if "status" in action.lower():
            action_icon = "🔄"
        elif "priority" in action.lower():
            action_icon = "🎯"
        elif "assignee" in action.lower():
            action_icon = "👤"
        elif "created" in action.lower():
            action_icon = "✨"
        elif "project" in action.lower():
            action_icon = "📁"
        elif "due" in action.lower():
            action_icon = "📅"
        elif "title" in action.lower():
            action_icon = "✏️"
        elif "description" in action.lower():
            action_icon = "📄"
        elif "collaborator" in action.lower():
            action_icon = "🤝"
        
        result += f"{action_icon} **{action}** by {entry.user_name}\n"
        result += f"   📅 {timestamp}\n"
        
        # Show field change details
        if entry.field_name:
            if entry.old_value is not None and entry.new_value is not None:
                result += f"   Changed `{entry.field_name}`: {entry.old_value} → {entry.new_value}\n"
            elif entry.new_value is not None:
                result += f"   Set `{entry.field_name}`: {entry.new_value}\n"
        
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
def get_task_history(task_title: str, current_user_id: str, company_id: str, skip: int = 0, limit: int = 50):
    """Get the activity history of a task - shows what changed and when.
    Displays changes including status updates, priority changes, assignee changes, due date updates, etc.
    
    Searches for the task by title (case-insensitive, supports partial matching).
    
    Parameters:
    - task_title: The title/name of the task to search for (partial match supported)
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    - skip: Number of history entries to skip (for pagination, default 0)
    - limit: Maximum number of history entries to return (default 50)
    
    Example usage:
    - "Show history for task 'Design Homepage'"
    - "Get history of the Login Page task"
    - "What changes were made to the API integration task?"
    """
    return run_async(_get_task_history_async(task_title, current_user_id, company_id, skip, limit))


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


# --- Async Invitation Operations ---

async def _send_invitation_async(
    invitee_email: str,
    current_user_id: str,
    company_id: str,
    role: str = "Member"
):
    """Async implementation of send invitation."""
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.company import Company
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    from datetime import timedelta
    import re
    
    # Validate email format using simple regex
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    invitee_email = invitee_email.strip()
    if not re.match(email_pattern, invitee_email):
        return f"Error: Invalid email address '{invitee_email}'. Please provide a valid email."
    
    # Get current user (must be admin)
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Check if user is admin (handle both enum and string comparison)
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if user_role != "Admin" and user_role.lower() != "admin":
        return "Error: Only admins can send invitations. Please contact your administrator."
    
    # Get company info
    company = await Company.get(company_id)
    if not company:
        return "Error: Company not found."
    
    # Check if email belongs to someone already in the company
    try:
        existing_users = await User.find({"email": invitee_email}).to_list()
        existing_user = existing_users[0] if existing_users else None
        if existing_user:
            # Check if already a member
            existing_company_ids = existing_user.get_effective_company_ids() if hasattr(existing_user, 'get_effective_company_ids') else []
            if company_id in existing_company_ids:
                return f"Error: User with email '{invitee_email}' is already a member of {company.name}."
    except Exception as e:
        logger.warning(f"Error checking existing user: {e}")
        existing_user = None
    
    # Check if invitation already exists and is pending
    try:
        status_value = InvitationStatus.PENDING.value if hasattr(InvitationStatus.PENDING, 'value') else str(InvitationStatus.PENDING)
        existing_invitations = await Invitation.find({
            "invitee_email": invitee_email,
            "company_id": company_id,
            "status": status_value
        }).to_list()
        existing_invitation = existing_invitations[0] if existing_invitations else None
    except Exception as e:
        logger.warning(f"Error checking existing invitation: {e}")
        existing_invitation = None
    
    if existing_invitation:
        return f"Error: A pending invitation has already been sent to '{invitee_email}' for {company.name}."
    
    # Validate role
    valid_roles = [r.value for r in UserRole]
    if role not in valid_roles:
        return f"Error: Invalid role '{role}'. Valid roles are: {', '.join(valid_roles)}"
    
    # Create invitation
    expires_at = datetime.utcnow() + timedelta(days=30)  # 30-day expiry
    
    new_invitation = Invitation(
        invitee_email=invitee_email,
        invitee_user_id=str(existing_user.id) if existing_user else None,
        company_id=company_id,
        company_name=company.name,
        inviter_id=current_user_id,
        inviter_name=current_user.name,
        role=role,
        status=InvitationStatus.PENDING,
        expires_at=expires_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    await new_invitation.insert()
    
    # Notify via WebSocket that chatbot sent an invitation (broadcasts to company)
    await _notify_chatbot_db_change(
        company_id,
        "invitation_sent",
        {"invitation_id": str(new_invitation.id), "invitee_email": invitee_email, "role": role}
    )
    
    # Also send a direct notification to the invitee user if they exist
    if existing_user:
        await _notify_invitation_to_user(
            str(existing_user.id),
            {
                "id": str(new_invitation.id),
                "invitee_email": invitee_email,
                "invitee_user_id": str(existing_user.id),
                "company_id": company_id,
                "company_name": company.name,
                "inviter_id": current_user_id,
                "inviter_name": current_user.name,
                "role": role,
                "status": "Pending",
                "created_at": new_invitation.created_at.isoformat() if new_invitation.created_at else None,
                "updated_at": new_invitation.updated_at.isoformat() if new_invitation.updated_at else None,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "message": f"You have been invited to join {company.name}"
            }
        )
    
    return f"""✅ **Invitation Sent Successfully!**

📧 **Invitee Email:** {invitee_email}
🏢 **Company:** {company.name}
👤 **Role:** {role}
📅 **Expires:** {expires_at.strftime('%Y-%m-%d')}

The user will receive an invitation to join your company and can accept or decline it."""


async def _list_received_invitations_async(current_user_id: str):
    """Async implementation of list received invitations."""
    from dash_api.app.models.user import User
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    
    # Get current user
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Find invitations sent to this user's email
    try:
        invitations = await Invitation.find({
            "invitee_email": current_user.email
        }).sort([("created_at", -1)]).to_list()
    except Exception as e:
        logger.warning(f"Error fetching received invitations: {e}")
        return "📭 **No Invitations**\n\nYou haven't received any company invitations yet."
    
    if not invitations:
        return "📭 **No Invitations**\n\nYou haven't received any company invitations yet."
    
    # Group by status for better display
    pending = [inv for inv in invitations if inv.status == InvitationStatus.PENDING]
    accepted = [inv for inv in invitations if inv.status == InvitationStatus.ACCEPTED]
    declined = [inv for inv in invitations if inv.status == InvitationStatus.DECLINED]
    
    result = "📬 **Your Invitations**\n\n"
    
    if pending:
        result += "🔔 **Pending Invitations:**\n"
        for inv in pending:
            expires_str = inv.expires_at.strftime("%Y-%m-%d") if inv.expires_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Expires: {expires_str})\n"
            result += f"    Sent by: {inv.inviter_name}\n"
        result += "\n"
    
    if accepted:
        result += "✅ **Accepted Invitations:**\n"
        for inv in accepted:
            joined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Joined: {joined_str})\n"
        result += "\n"
    
    if declined:
        result += "❌ **Declined Invitations:**\n"
        for inv in declined:
            declined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.company_name}** - Role: {inv.role} (Declined: {declined_str})\n"
    
    return result


async def _list_sent_invitations_async(current_user_id: str, company_id: str):
    """Async implementation of list sent invitations - for admins."""
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.company import Company
    from dash_api.app.models.invitation import Invitation, InvitationStatus
    
    # Get current user (must be admin)
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Check if user is admin (handle both enum and string comparison)
    user_role = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
    if user_role != "Admin" and user_role.lower() != "admin":
        return "Error: Only admins can view sent invitations."
    
    # Get company info
    company = await Company.get(company_id)
    if not company:
        return "Error: Company not found."
    
    # Find invitations sent from this company
    try:
        invitations = await Invitation.find({
            "company_id": company_id
        }).sort([("created_at", -1)]).to_list()
    except Exception as e:
        logger.warning(f"Error fetching sent invitations: {e}")
        return f"📭 **No Invitations Sent**\n\nNo invitations have been sent from {company.name} yet."
    
    if not invitations:
        return f"📭 **No Invitations Sent**\n\nNo invitations have been sent from {company.name} yet."
    
    # Group by status
    pending = [inv for inv in invitations if inv.status == InvitationStatus.PENDING]
    accepted = [inv for inv in invitations if inv.status == InvitationStatus.ACCEPTED]
    declined = [inv for inv in invitations if inv.status == InvitationStatus.DECLINED]
    
    result = f"📤 **Invitations Sent from {company.name}**\n\n"
    
    if pending:
        result += f"🔔 **Pending ({len(pending)}):**\n"
        for inv in pending:
            expires_str = inv.expires_at.strftime("%Y-%m-%d") if inv.expires_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Expires: {expires_str})\n"
        result += "\n"
    
    if accepted:
        result += f"✅ **Accepted ({len(accepted)}):**\n"
        for inv in accepted:
            joined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Joined: {joined_str})\n"
        result += "\n"
    
    if declined:
        result += f"❌ **Declined ({len(declined)}):**\n"
        for inv in declined:
            declined_str = inv.updated_at.strftime("%Y-%m-%d") if inv.updated_at else "N/A"
            result += f"  • **{inv.invitee_email}** - Role: {inv.role} (Declined: {declined_str})\n"
    
    return result


# --- LangGraph Invitation Tools ---

@tool
def send_invitation(invitee_email: str, current_user_id: str, company_id: str, role: str = "Member"):
    """Send an invitation to a user to join your company.
    ADMIN ONLY - Only administrators can send invitations.
    
    Parameters:
    - invitee_email: The email address of the person to invite (e.g., "john@example.com")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    - role: Role to assign upon acceptance - "Admin", "Member", or "Viewer" (default: "Member")
    
    Example usage:
    - "Send an invitation to samriddhi@email.com"
    - "Invite john@company.com as an Admin"
    - "Send invitation to user@example.com with Member role"
    
    Note:
    - Invitations expire after 30 days
    - The recipient will receive a notification and can accept or decline
    - User must not already be a member of your company
    """
    return run_async(_send_invitation_async(invitee_email, current_user_id, company_id, role))


@tool
def list_received_invitations(current_user_id: str):
    """List all invitations you have received from companies.
    Shows pending, accepted, and declined invitations.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    
    Example usage:
    - "Show me my invitations"
    - "What invitations have I received?"
    - "List all my pending invitations"
    """
    return run_async(_list_received_invitations_async(current_user_id))


@tool
def list_sent_invitations(current_user_id: str, company_id: str):
    """List all invitations sent from your company.
    ADMIN ONLY - Shows pending, accepted, and declined invitations.
    
    Parameters:
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example usage:
    - "Show me all invitations we've sent"
    - "Who have we invited to join?"
    - "List pending invitations"
    """
    return run_async(_list_sent_invitations_async(current_user_id, company_id))


# --- Async Project Update Operations ---

async def _update_project_name_async(project_name: str, new_name: str, current_user_id: str, company_id: str):
    """Async implementation of update project name."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.task import Task
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions - owner or admin can update
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if project.owner_id != current_user_id and current_user.role != UserRole.ADMIN:
        return "Error: Only the project owner or an admin can update this project."
    
    old_name = project.name
    project.name = new_name
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Update project_name in all associated tasks
    tasks = await Task.find({"project_id": str(project.id)}).to_list()
    for task in tasks:
        task.project_name = new_name
        await task.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_name_updated",
        {"project_id": str(project.id), "old_name": old_name, "new_name": new_name}
    )
    
    return f"Project name updated from '{old_name}' to '{new_name}'."


async def _update_project_status_async(project_name: str, new_status: str, current_user_id: str, company_id: str):
    """Async implementation of update project status."""
    from dash_api.app.models.project import Project, ProjectStatus
    from dash_api.app.models.user import User, UserRole
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if project.owner_id != current_user_id and current_user.role != UserRole.ADMIN:
        return "Error: Only the project owner or an admin can update this project."
    
    # Map status string to enum
    status_map = {
        "active": ProjectStatus.ACTIVE,
        "archived": ProjectStatus.ARCHIVED,
        "on hold": ProjectStatus.ON_HOLD,
        "onhold": ProjectStatus.ON_HOLD,
        "on-hold": ProjectStatus.ON_HOLD
    }
    
    mapped_status = status_map.get(new_status.lower())
    if not mapped_status:
        return f"Error: Invalid status '{new_status}'. Valid options: Active, Archived, On Hold"
    
    old_status = project.status.value if project.status else "Active"
    project.status = mapped_status
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_status_updated",
        {"project_id": str(project.id), "project_name": project.name, "old_status": old_status, "new_status": mapped_status.value}
    )
    
    return f"Project '{project.name}' status updated from '{old_status}' to '{mapped_status.value}'."


async def _update_project_client_async(project_name: str, new_client: str, current_user_id: str, company_id: str):
    """Async implementation of update project client."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if project.owner_id != current_user_id and current_user.role != UserRole.ADMIN:
        return "Error: Only the project owner or an admin can update this project."
    
    old_client = project.client_name
    project.client_name = new_client
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_client_updated",
        {"project_id": str(project.id), "project_name": project.name, "old_client": old_client, "new_client": new_client}
    )
    
    return f"Project '{project.name}' client updated from '{old_client}' to '{new_client}'."


async def _update_project_owner_async(project_name: str, new_owner_name: str, current_user_id: str, company_id: str):
    """Async implementation of update project owner."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions - only admin can change project owner
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if current_user.role != UserRole.ADMIN:
        return "Error: Only admins can change project ownership."
    
    # Find the new owner by name
    new_owner = await _find_user_by_name_async(new_owner_name, current_user_id, company_id)
    if not new_owner:
        users_list = await _list_users_async(current_user_id, company_id)
        return f"Error: Could not find a user named '{new_owner_name}'.\n\nHere are the available users:\n{users_list}"
    
    new_owner_user = await User.get(new_owner["id"])
    if not new_owner_user:
        return "Error: New owner user not found."
    
    old_owner_name = project.owner_name
    project.owner_id = new_owner["id"]
    project.owner_name = new_owner_user.name
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_owner_updated",
        {"project_id": str(project.id), "project_name": project.name, "old_owner": old_owner_name, "new_owner": new_owner_user.name}
    )
    
    return f"Project '{project.name}' owner changed from '{old_owner_name}' to '{new_owner_user.name}'."


async def _update_project_deadline_async(project_name: str, new_deadline: str, current_user_id: str, company_id: str):
    """Async implementation of update project deadline."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if project.owner_id != current_user_id and current_user.role != UserRole.ADMIN:
        return "Error: Only the project owner or an admin can update this project."
    
    # Handle removing deadline
    if not new_deadline or new_deadline.lower() in ["none", "remove", "clear"]:
        old_deadline = project.due_date.strftime("%Y-%m-%d") if project.due_date else "None"
        project.due_date = None
        project.updated_at = datetime.utcnow()
        await project.save()
        
        await _notify_chatbot_db_change(
            company_id,
            "project_deadline_updated",
            {"project_id": str(project.id), "project_name": project.name, "old_deadline": old_deadline, "new_deadline": "None"}
        )
        
        return f"Project '{project.name}' deadline removed (was '{old_deadline}')."
    
    # Parse new deadline
    try:
        parsed_date = datetime.strptime(new_deadline, "%Y-%m-%d")
    except ValueError:
        return "Error: Invalid date format. Use YYYY-MM-DD format (e.g., 2024-12-31)."
    
    old_deadline = project.due_date.strftime("%Y-%m-%d") if project.due_date else "None"
    project.due_date = parsed_date
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_deadline_updated",
        {"project_id": str(project.id), "project_name": project.name, "old_deadline": old_deadline, "new_deadline": new_deadline}
    )
    
    return f"Project '{project.name}' deadline updated from '{old_deadline}' to '{new_deadline}'."


async def _update_project_description_async(project_name: str, new_description: str, current_user_id: str, company_id: str):
    """Async implementation of update project description."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Check permissions
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    if project.owner_id != current_user_id and current_user.role != UserRole.ADMIN:
        return "Error: Only the project owner or an admin can update this project."
    
    old_description = project.description[:50] + "..." if len(project.description) > 50 else project.description
    project.description = new_description
    project.updated_at = datetime.utcnow()
    await project.save()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_description_updated",
        {"project_id": str(project.id), "project_name": project.name}
    )
    
    return f"Project '{project.name}' description updated successfully."


async def _add_task_to_project_async(task_title: str, project_name: str, current_user_id: str, company_id: str):
    """Async implementation of add task to project."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User, UserRole
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    
    # Find the task
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Find the project
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    # Check if task is already in this project
    if task.project_id == str(project.id):
        return f"Task '{task.title}' is already in project '{project.name}'."
    
    old_project_name = task.project_name or "No project"
    task.project_id = str(project.id)
    task.project_name = project.name
    task.updated_at = datetime.utcnow()
    await task.save()
    
    # Create history entry
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.PROJECT_CHANGED,
        field_name="project",
        old_value=old_project_name,
        new_value=project.name,
        user_id=current_user_id,
        user_name=current_user.name,
        user_avatar=current_user.avatar_url if hasattr(current_user, 'avatar_url') else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_task_added",
        {"project_id": str(project.id), "project_name": project.name, "task_id": str(task.id), "task_title": task.title}
    )
    
    return f"Task '{task.title}' has been added to project '{project.name}'."


async def _remove_task_from_project_async(task_title: str, current_user_id: str, company_id: str):
    """Async implementation of remove task from its project."""
    from dash_api.app.models.task import Task
    from dash_api.app.models.user import User
    from dash_api.app.models.task_history import TaskHistory, HistoryActionType
    
    # Find the task
    task = await _find_task_by_title_async(task_title, current_user_id, company_id)
    if not task:
        return f"Error: Task '{task_title}' not found. Please check the task name and try again."
    
    # Authorization check
    if task.company_id != company_id:
        return "Error: Task not found or permission denied."
    
    if not task.project_id:
        return f"Task '{task.title}' is not associated with any project."
    
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."
    
    old_project_name = task.project_name or "Unknown project"
    task.project_id = None
    task.project_name = None
    task.updated_at = datetime.utcnow()
    await task.save()
    
    # Create history entry
    history = TaskHistory(
        task_id=str(task.id),
        action=HistoryActionType.PROJECT_CHANGED,
        field_name="project",
        old_value=old_project_name,
        new_value="None",
        user_id=current_user_id,
        user_name=current_user.name,
        user_avatar=current_user.avatar_url if hasattr(current_user, 'avatar_url') else None,
        company_id=company_id
    )
    await history.insert()
    
    # Notify via WebSocket
    await _notify_chatbot_db_change(
        company_id,
        "project_task_removed",
        {"old_project_name": old_project_name, "task_id": str(task.id), "task_title": task.title}
    )
    
    return f"Task '{task.title}' has been removed from project '{old_project_name}'."


async def _get_project_tasks_async(project_name: str, current_user_id: str, company_id: str):
    """Async implementation of get project tasks."""
    from dash_api.app.models.task import Task, TaskStatus
    from dash_api.app.models.project import Project
    
    project = await _find_project_by_name_async(project_name, company_id)
    if not project:
        projects_list = await _list_projects_async(current_user_id, company_id)
        return f"Error: Could not find a project named '{project_name}'.\n\nHere are the available projects:\n{projects_list}"
    
    # Get all tasks for this project
    tasks = await Task.find({"project_id": str(project.id), "company_id": company_id}).to_list()
    
    if not tasks:
        return f"📁 **{project.name}**\n\n📋 No tasks found in this project."
    
    # Format task list
    result = f"📁 **{project.name}**\n\n📋 **Tasks ({len(tasks)}):**\n\n"
    
    for task in tasks:
        status_icon = "⬜"
        if task.status == TaskStatus.IN_PROGRESS:
            status_icon = "🔄"
        elif task.status == TaskStatus.REVIEW:
            status_icon = "👀"
        elif task.status == TaskStatus.DONE:
            status_icon = "✅"
        
        priority_icon = ""
        if hasattr(task, 'priority') and task.priority:
            priority_val = task.priority.value if hasattr(task.priority, 'value') else str(task.priority)
            if priority_val == "High":
                priority_icon = "🔴"
            elif priority_val == "Medium":
                priority_icon = "🟡"
            else:
                priority_icon = "🟢"
        
        due_str = ""
        if task.due_date:
            due_str = f" (Due: {task.due_date.strftime('%Y-%m-%d') if isinstance(task.due_date, datetime) else str(task.due_date)})"
        
        result += f"{status_icon} {priority_icon} **{task.title}** - {task.assignee_name}{due_str}\n"
    
    return result


# --- LangGraph Project Update Tools ---

@tool
def update_project_name(project_name: str, new_name: str, current_user_id: str, company_id: str):
    """Update the name of a project.
    
    Parameters:
    - project_name: Current name of the project to update
    - new_name: New name for the project
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Rename project 'Alpha' to 'Alpha 2.0'"
    """
    return run_async(_update_project_name_async(project_name, new_name, current_user_id, company_id))


@tool
def update_project_status(project_name: str, new_status: str, current_user_id: str, company_id: str):
    """Update the status of a project.
    
    Parameters:
    - project_name: Name of the project to update
    - new_status: New status - "Active", "Archived", or "On Hold"
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Set project 'Alpha' status to On Hold"
    """
    return run_async(_update_project_status_async(project_name, new_status, current_user_id, company_id))


@tool
def update_project_client(project_name: str, new_client: str, current_user_id: str, company_id: str):
    """Update the client of a project.
    
    Parameters:
    - project_name: Name of the project to update
    - new_client: New client name
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Change client for project 'Alpha' to 'Acme Corp'"
    """
    return run_async(_update_project_client_async(project_name, new_client, current_user_id, company_id))


@tool
def update_project_owner(project_name: str, new_owner_name: str, current_user_id: str, company_id: str):
    """Update the owner of a project. ADMIN ONLY.
    
    Parameters:
    - project_name: Name of the project to update
    - new_owner_name: Name of the new project owner (e.g., "John", "Samriddhi")
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Make Samriddhi the owner of project 'Alpha'"
    """
    return run_async(_update_project_owner_async(project_name, new_owner_name, current_user_id, company_id))


@tool
def update_project_deadline(project_name: str, new_deadline: str, current_user_id: str, company_id: str):
    """Update the deadline/due date of a project.
    
    Parameters:
    - project_name: Name of the project to update
    - new_deadline: New deadline in YYYY-MM-DD format, or "none" to remove
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Set deadline for project 'Alpha' to 2025-03-15"
    """
    return run_async(_update_project_deadline_async(project_name, new_deadline, current_user_id, company_id))


@tool
def update_project_description(project_name: str, new_description: str, current_user_id: str, company_id: str):
    """Update the description of a project.
    
    Parameters:
    - project_name: Name of the project to update
    - new_description: New description text
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Update description of project 'Alpha' to 'New mobile app development'"
    """
    return run_async(_update_project_description_async(project_name, new_description, current_user_id, company_id))


@tool
def add_task_to_project(task_title: str, project_name: str, current_user_id: str, company_id: str):
    """Add a task to a project.
    
    Parameters:
    - task_title: Title of the task to add to the project
    - project_name: Name of the project to add the task to
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Add task 'Design Homepage' to project 'Alpha'"
    """
    return run_async(_add_task_to_project_async(task_title, project_name, current_user_id, company_id))


@tool
def remove_task_from_project(task_title: str, current_user_id: str, company_id: str):
    """Remove a task from its current project.
    
    Parameters:
    - task_title: Title of the task to remove from its project
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Remove task 'Design Homepage' from its project"
    """
    return run_async(_remove_task_from_project_async(task_title, current_user_id, company_id))


@tool
def get_project_tasks(project_name: str, current_user_id: str, company_id: str):
    """Get all tasks associated with a project.
    
    Parameters:
    - project_name: Name of the project to get tasks for
    - current_user_id: Current logged-in user ID (auto-populated)
    - company_id: Current company ID (auto-populated)
    
    Example: "Show all tasks in project 'Alpha'"
    """
    return run_async(_get_project_tasks_async(project_name, current_user_id, company_id))


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
    update_task_due_date,
    update_task_project,
    delete_task,
    list_projects,
    get_project_info,
    get_task_stats,
    get_task_collaborators,
    get_task_history,
    get_task_comments,
    send_invitation,
    list_received_invitations,
    list_sent_invitations,
    # Project update tools
    update_project_name,
    update_project_status,
    update_project_client,
    update_project_owner,
    update_project_deadline,
    update_project_description,
    add_task_to_project,
    remove_task_from_project,
    get_project_tasks
]
