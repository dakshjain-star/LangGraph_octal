from langchain_core.tools import tool
from bson.objectid import ObjectId
from typing import Optional
import json
from datetime import datetime
from model import db

# --- Database Tools ---
@tool
def create_task(
    title: str, 
    start_date: str, 
    end_date: str, 
    assignee_email: str, 
    current_user_id: str,
    description: Optional[str] = None,
    priority: Optional[str] = None
):
    """Create a new task.
    
    Required fields:
    - title: Task title (required)
    - start_date: Task start date in YYYY-MM-DD format (required)
    - end_date: Task end date in YYYY-MM-DD format (required)
    - assignee_email: Email address of the person assigned to the task (required)
    - current_user_id: Current logged-in user ID (auto-populated)
    
    Optional fields:
    - description: Task description (optional)
    - priority: Task priority like Low, Medium, High (optional)
    """
    # Find assignee by email
    assignee = db.users.find_one({"email": assignee_email})
    
    if not assignee:
        return "Error: Assignee email not found in the organization."
    
    # Check if user is trying to assign task to themselves
    if str(assignee["_id"]) == current_user_id:
        return "Error: You cannot assign a task to yourself. Please assign it to another user."
    
    new_task = {
        "title": title,
        "description": description if description else "",
        "priority": priority if priority else "Normal",
        "start_date": start_date,
        "end_date": end_date,
        "assigned_by": ObjectId(current_user_id),
        "assignee": assignee["_id"],
        "timestamp": datetime.now()
    }
    result = db.tasks.insert_one(new_task)
    return f"Task created successfully with ID: {str(result.inserted_id)}"

@tool
def list_users(current_user_id: str):
    """List all users in the organization with their full names and email addresses.
    This helps identify who can be assigned tasks."""
    users = list(db.users.find({}, {"first_name": 1, "last_name": 1, "email": 1, "_id": 0}))
    if not users:
        return "No users found in the organization."
    
    user_list = []
    for user in users:
        full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        email = user.get('email', 'N/A')
        
        # Truncate extremely long emails to prevent display issues
        # Keep first 50 chars and show indication if truncated
        if len(email) > 50:
            email_display = f"{email[:50]}... (the email field is truncated)"
        else:
            email_display = email
            
        user_list.append(f"- **{full_name}** ({email_display})")
    
    return "\n".join(user_list)

@tool
def view_my_tasks(current_user_id: str):
    """Fetch tasks for the current user (assignee or assigner)."""
    uid = ObjectId(current_user_id)
    query = {"$or": [{"assignee": uid}, {"assigned_by": uid}]}
    tasks = list(db.tasks.find(query))
    if not tasks: return "No tasks found."
    
    # Return structured JSON for the LLM to parse easily
    task_list = []
    for t in tasks:
        # Fetch full user details for display
        assignee_doc = db.users.find_one({"_id": t.get("assignee")})
        assigner_doc = db.users.find_one({"_id": t.get("assigned_by")})
        
        # Build full name with email (no user ID)
        if assignee_doc:
            assignee_first = assignee_doc.get("first_name", "")
            assignee_last = assignee_doc.get("last_name", "")
            assignee_email = assignee_doc.get("email", "")
            assignee_display = f"{assignee_first} {assignee_last}, {assignee_email}".strip()
        else:
            assignee_display = "Unknown"
        
        if assigner_doc:
            assigner_first = assigner_doc.get("first_name", "")
            assigner_last = assigner_doc.get("last_name", "")
            assigner_email = assigner_doc.get("email", "")
            assigner_display = f"{assigner_first} {assigner_last}, {assigner_email}".strip()
        else:
            assigner_display = "Unknown"

        task_list.append({
            "id": str(t['_id']),
            "title": t.get('title', 'Untitled'),
            "description": t.get('description', 'No description'),
            "priority": t.get('priority', 'Normal'),
            "start_date": t.get('start_date', 'N/A'),
            "end_date": t.get('end_date', 'TBD'),
            "assigned_by": assigner_display,
            "assignee": assignee_display
        })
    return json.dumps(task_list)

@tool
def update_task_priority(task_id: str, new_priority: str, current_user_id: str):
    """Update task priority. User must own the task."""
    uid = ObjectId(current_user_id)
    # Authorization check
    task = db.tasks.find_one({"_id": ObjectId(task_id), "$or": [{"assignee": uid}, {"assigned_by": uid}]})
    if not task: return "Error: Task not found or permission denied."
    
    db.tasks.update_one({"_id": ObjectId(task_id)}, {"$set": {"priority": new_priority}})
    return f"Task {task_id} priority updated to {new_priority}."

@tool
def delete_task(task_id: str, current_user_id: str):
    """Delete a task. User must own the task (be assignee or assigner)."""
    uid = ObjectId(current_user_id)
    # Authorization check
    task = db.tasks.find_one({"_id": ObjectId(task_id), "$or": [{"assignee": uid}, {"assigned_by": uid}]})
    if not task: return "Error: Task not found or permission denied."
    
    db.tasks.delete_one({"_id": ObjectId(task_id)})
    return f"Task {task_id} deleted successfully."

# List of all tools for export
tools = [create_task, view_my_tasks, update_task_priority, delete_task, list_users]
