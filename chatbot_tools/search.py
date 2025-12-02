"""
Search/lookup helper functions for finding tasks, users, and projects.
Used by task, project, and invitation tools.
"""
import logging
import sys
import os

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'dash_api'))

logger = logging.getLogger(__name__)


async def _find_task_by_title_async(title_query: str, current_user_id: str, company_id: str):
    """Find a task by title (partial match) in the company.
    
    Search priority:
    1. Exact match (case-insensitive)
    2. Title contains the query
    3. Query contains the title
    4. Word-based partial match
    """
    from dash_api.app.models.task import Task
    
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


async def _find_user_by_name_async(name_query: str, current_user_id: str, company_id: str):
    """Find a user by name (partial match) in the same company."""
    from dash_api.app.models.user import User, UserStatus
    
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
