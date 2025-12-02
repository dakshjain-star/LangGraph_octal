"""
Project-related tools and async operations for LangGraph chatbot.
Handles project listing, info retrieval, and updates.
"""
from langchain_core.tools import tool
from datetime import datetime
import sys
import os
import logging

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dash_api'))

from .helpers import run_async, _notify_chatbot_db_change
from .search import (
    _find_task_by_title_async,
    _find_project_by_name_async,
    _find_user_by_name_async,
    _list_users_async,
    _list_projects_async
)

logger = logging.getLogger(__name__)


# --- Async Project Operations ---

async def _get_project_info_async(project_name: str, current_user_id: str, company_id: str):
    """Async implementation of get project info by name."""
    from dash_api.app.models.project import Project
    from dash_api.app.models.task import Task
    import json
    
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
    
    old_description = project.description[:50] + "..." if project.description and len(project.description) > 50 else (project.description or "")
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


async def _create_project_async(project_name: str, description: str, client_name: str, current_user_id: str, company_id: str):
    """Async implementation to create a new project.

    Parameters:
    - project_name: Name of the new project (must be unique within company)
    - description: Project description (required)
    - client_name: Client name (optional, defaults to 'General')
    - current_user_id: ID of the user creating the project
    - company_id: Company ID for multi-tenancy
    """
    from dash_api.app.models.project import Project
    from dash_api.app.models.user import User

    # Basic validation
    if not project_name or not project_name.strip():
        return "Error: Project name cannot be empty."

    if not description or not description.strip():
        return "Error: Description cannot be empty. Please provide a short description for the project."

    # Check duplicate by name within company
    existing = await _find_project_by_name_async(project_name, company_id)
    if existing:
        return f"Error: A project named '{project_name}' already exists."

    # Resolve current user
    current_user = await User.get(current_user_id)
    if not current_user:
        return "Error: Current user not found."

    owner_id = current_user_id
    owner_name = current_user.name

    client = client_name.strip() if client_name and client_name.strip() else "General"

    # Build project document
    project = Project(
        name=project_name.strip(),
        description=description.strip(),
        client_name=client,
        owner_id=owner_id,
        owner_name=owner_name,
        company_id=company_id,
        company_name=(current_user.current_company_name or current_user.company_name) if hasattr(current_user, 'current_company_name') or hasattr(current_user, 'company_name') else None,
    )

    # Insert into DB
    await project.insert()

    # Notify via WebSocket about the new project
    await _notify_chatbot_db_change(
        company_id,
        "project_created",
        {"project_id": str(project.id), "project_name": project.name}
    )

    return f"Project '{project.name}' created successfully." 


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


# --- LangGraph Project Tools (Sync Wrappers) ---

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
def create_project(project_name: str, description: str, client_name: str, current_user_id: str, company_id: str):
    """Create a new project in the company.

    Parameters:
    - project_name: Name for the new project
    - description: Short description of the project
    - client_name: Client name (optional)
    - current_user_id: Current user creating the project (auto-populated)
    - company_id: Company ID (auto-populated)
    """
    return run_async(_create_project_async(project_name, description, client_name, current_user_id, company_id))

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


# Export all project tools
project_tools = [
    list_projects,
    get_project_info,
    create_project,
    update_project_name,
    update_project_status,
    update_project_client,
    update_project_owner,
    update_project_deadline,
    update_project_description,
    add_task_to_project,
    remove_task_from_project,
    get_project_tasks,
]
