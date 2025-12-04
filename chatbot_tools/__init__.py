"""
LangGraph Chatbot Tools Package.

This package provides modular chatbot tools for task management, project management,
and invitation handling. It uses async Beanie ODM models matching the dash_saas system.

Usage:
    from chatbot_tools import tools, set_main_loop
    
    # Set the main event loop (call from FastAPI startup)
    set_main_loop(loop)
    
    # Use tools with LangGraph
    llm.bind_tools(tools)
"""
import sys
import os

# Add dash_api to path for all modules
# Add parent directory to path to allow importing dash_api
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import core helpers
from .helpers import (
    set_main_loop,
    get_main_loop,
    run_async,
    _notify_chatbot_db_change,
    _notify_invitation_to_user,
    DASH_API_BASE_URL,
)

# Import search helpers (for use by other modules or external code)
from .search import (
    _find_task_by_title_async,
    _find_project_by_name_async,
    _find_user_by_name_async,
    _list_users_async,
    _list_projects_async,
)

# Import task tools
from .tasks import (
    task_tools,
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
    get_task_stats,
    get_task_collaborators,
    get_task_history,
    get_task_comments,
    post_task_comment,
)

# Import project tools
from .projects import (
    project_tools,
    list_projects,
    get_project_info,
    update_project_name,
    update_project_status,
    update_project_client,
    update_project_owner,
    update_project_deadline,
    update_project_description,
    add_task_to_project,
    remove_task_from_project,
    get_project_tasks,
    create_project,
    get_project_due_date,
)

# Import invitation tools
from .invitations import (
    invitation_tools,
    send_invitation,
    list_received_invitations,
    list_sent_invitations,
)

# Import profile tools factory
from .profile import create_profile_tools


# Combined list of all tools for export (matching original tools.py order)
tools = [
    # Task tools
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
    # Project basic tools
    list_projects,
    get_project_info,
    get_project_due_date,
    create_project,
    # Task stats/info tools
    get_task_stats,
    get_task_collaborators,
    get_task_history,
    get_task_comments,
    post_task_comment,
    # Invitation tools
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
    get_project_tasks,
]

# Public API
__all__ = [
    # Core helpers
    'set_main_loop',
    'get_main_loop',
    'run_async',
    'DASH_API_BASE_URL',
    
    # All tools combined
    'tools',
    'task_tools',
    'project_tools',
    'invitation_tools',
    'create_profile_tools',
    
    # Task tools
    'create_task',
    'list_users',
    'view_my_tasks',
    'view_all_my_tasks',
    'view_user_tasks',
    'search_user_tasks',
    'view_all_company_tasks',
    'update_task_status',
    'update_task_priority',
    'update_task_due_date',
    'update_task_project',
    'delete_task',
    'get_task_stats',
    'get_task_collaborators',
    'get_task_history',
    'get_task_comments',
    'post_task_comment',
    
    # Project tools
    'list_projects',
    'get_project_info',
    'create_project',
    'update_project_name',
    'update_project_status',
    'update_project_client',
    'update_project_owner',
    'update_project_deadline',
    'update_project_description',
    'add_task_to_project',
    'remove_task_from_project',
    'get_project_tasks',
    'get_project_due_date',
    
    # Invitation tools
    'send_invitation',
    'list_received_invitations',
    'list_sent_invitations',
]
