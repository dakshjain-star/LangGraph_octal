import os
from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from bson.objectid import ObjectId
import pymongo
import bcrypt
import warnings
import json
from datetime import datetime

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*Pydantic V1.*")

# --- Database Connection (Same as before) ---
client = pymongo.MongoClient("mongodb+srv://octaldaksh:octal123@cluster0.5xt6n.mongodb.net/")
db = client["db_octal"]

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: Optional[str]
    user_name: Optional[str]

# --- Database Tools (Same logic, compacted for brevity) ---
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
        user_list.append(f"- **{full_name}** ({email})")
    
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
        # Fetch names for display
        assignee_doc = db.users.find_one({"_id": t.get("assignee")})
        assigner_doc = db.users.find_one({"_id": t.get("assigned_by")})
        
        assignee_name = assignee_doc.get("first_name", "Unknown") if assignee_doc else "Unknown"
        assigner_name = assigner_doc.get("first_name", "Unknown") if assigner_doc else "Unknown"

        task_list.append({
            "id": str(t['_id']),
            "title": t.get('title', 'Untitled'),
            "description": t.get('description', 'No description'),
            "priority": t.get('priority', 'Normal'),
            "start_date": t.get('start_date', 'N/A'),
            "end_date": t.get('end_date', 'TBD'),
            "assigned_by": f"{assigner_name} ({str(t.get('assigned_by', 'N/A'))})",
            "assignee": f"{assignee_name} ({str(t.get('assignee', 'N/A'))})"
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

# --- INITIALIZE OLLAMA ---
# We use the specific model you requested.
# ensure "ollama serve" is running in your terminal.

tools = [create_task, view_my_tasks, update_task_priority, delete_task, list_users]

llm = ChatOllama(
    model="gpt-oss:120b-cloud",  # <--- YOUR SPECIFIC MODEL
    temperature=0,
    base_url="http://localhost:11434" # Default Ollama URL
).bind_tools(tools)

# --- Nodes ---

def login_node(state: AgentState):
    """Simple login logic."""
    last_msg = state["messages"][-1]
    content = last_msg.content.lower()
    
    if "login" in content:
        try:
            parts = last_msg.content.split()
            # login <email> <pass>
            email = parts[1]
            password = parts[2]
            
            user = db.users.find_one({"email": email})
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
                return {
                    "user_id": str(user["_id"]),
                    "user_name": user["first_name"],
                    "messages": [SystemMessage(content=f"Login successful. Welcome {user['first_name']}.")]
                }
        except:
            pass
    
    return {"messages": [SystemMessage(content="Please log in first: login <email> <password>")]}

def chatbot_node(state: AgentState):
    user_id = state["user_id"]
    
    # System prompt is critical for local models to understand they must use the ID
    sys_msg = SystemMessage(content=f"""
    You are a Task Manager Bot. Current User ID: {user_id}.
    
    CRITICAL INSTRUCTIONS:
    1. ALWAYS pass '{user_id}' as the 'current_user_id' argument to tools.
    2. Do not make up task IDs. Only use IDs given by the 'view_my_tasks' tool.
    3. When creating a task, you MUST collect these REQUIRED fields from the user:
       - Title (short name for the task)
       - Start Date (in YYYY-MM-DD format)
       - End Date (in YYYY-MM-DD format)
       - Assignee Email (the email address of person who will work on it)
       
       Optional fields (ask but don't require):
       - Description (what needs to be done)
       - Priority (e.g., Low, Medium, High)
       
       The 'assigned_by' field is automatically set to the current user ({user_id}).
       
    4. If the user asks for a list of users or who they can assign tasks to, use the 'list_users' tool.
       This will show all users' full names and email addresses (NO task information).
       
    5. When showing a list of tasks, format each task as a bulleted list item with nested details.
       Example format:
       * **Task Title** (ID: <id>)
         * **Description:** <desc>
         * **Priority:** <priority>
         * **Start Date:** <start>
         * **End Date:** <end>
         * **Assigned By:** <name + id>
         * **Assignee:** <name + id>
         
    6. If a user wants to create a task but doesn't provide all required information, ask them for the missing required fields.
    """)
    
    messages = [sys_msg] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}

from langgraph.prebuilt import ToolNode
tool_node = ToolNode(tools)

# --- Graph Construction ---
workflow = StateGraph(AgentState)

workflow.add_node("login_gate", login_node)
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", tool_node)

def route_check(state: AgentState):
    if state.get("user_id"): return "chatbot"
    return "login_gate"

def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

workflow.add_conditional_edges(START, route_check)
workflow.add_edge("login_gate", END)
workflow.add_conditional_edges("chatbot", should_continue)
workflow.add_edge("tools", "chatbot")

app = workflow.compile()

if __name__ == "__main__":
    print("=== Task Manager Chatbot ===")
    print("Commands: 'login <email> <password>' | 'exit' to quit")
    print("-" * 50)
    
    state = {
        "messages": [],
        "user_id": None,
        "user_name": None
    }
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ["exit", "quit", "bye"]:
            print("Goodbye!")
            break
        
        if not user_input:
            continue
        
        # Add user message to state
        state["messages"].append(HumanMessage(content=user_input))
        
        # Invoke the graph
        result = app.invoke(state)
        
        # Update state with result
        state = result
        
        # Print last bot response
        last_msg = state["messages"][-1]
        if hasattr(last_msg, 'content'):
            print(f"\nBot: {last_msg.content}")
        
        # Show tool calls if any (for debugging)
        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            print(f"[Tool calls made: {len(last_msg.tool_calls)}]")