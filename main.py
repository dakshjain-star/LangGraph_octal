"""
LangGraph Task Management Chatbot - Integrated with dash_saas.
Uses the same JWT authentication and database as the main dashboard API.
Includes real-time WebSocket updates for task history, comments, and collaborators.
"""
import asyncio
import os
import random
import sys
from typing import Annotated, Optional, Dict, Any
from typing_extensions import TypedDict
from contextlib import asynccontextmanager

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import ToolNode

import warnings
from datetime import datetime
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Add dash_api to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

# Import authentication from dash_api
from dash_api.app.services.auth import verify_token as dash_verify_token
from dash_api.app.config import settings as dash_settings

# Import database connection
from model import connect_db, close_db

# Import tools
from tools import tools, set_main_loop

# Import WebSocket client
from websocket_client import get_or_create_ws_handler, get_ws_handler, close_ws_handler

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*Pydantic V1.*")

# Security
security = HTTPBearer(auto_error=False)

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: Optional[str]
    user_name: Optional[str]
    company_id: Optional[str]


# --- INITIALIZE OLLAMA ---
llm = ChatOllama(
    model="gpt-oss:120b-cloud",
    temperature=0,
    base_url="http://localhost:11434"
).bind_tools(tools)


# --- System Prompt Builder ---
def build_system_prompt(user_id: str, user_name: str, company_id: str) -> str:
    """Create a dynamic task management system prompt."""
    assistant_roles = [
        "You are a helpful Task Management Assistant integrated into the Dash SaaS dashboard.",
        "Act as a Task Assistant focused on helping users manage their work assignments and deadlines.",
        "You are a Task Management co-pilot dedicated to helping users organize and track their tasks."
    ]
    
    display_name = user_name or "there"
    current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    return f"""
{random.choice(assistant_roles)}

**CRITICAL - REAL-TIME DATA REQUIREMENT:**
- Current Server Time: {current_time}
- ALWAYS use tools to fetch FRESH data from the database for EVERY query about tasks, users, or projects.
- NEVER rely on previously fetched data from earlier in the conversation - it may be stale.
- Data changes frequently in real-time. Always call the appropriate tool to get the current state.
- If a user asks about tasks, users, or projects, ALWAYS call the relevant tool first, even if you showed similar data before.

**Current User Context:**
- User ID: {user_id}
- User Name: {display_name}
- Company ID: {company_id}

**General Behavior:**
- Be helpful, friendly, and concise in your responses.
- When users greet you, respond warmly with "Hello {display_name}!" and offer assistance.
- When users say thank you, respond politely and ask if they need anything else.

**⚠️ MANDATORY: ALWAYS FETCH FRESH DATA**
- You MUST call the appropriate tool for EVERY request about tasks, users, or projects.
- NEVER reuse or reference data from previous messages - it is likely outdated.
- Even if the user asks the same question twice, ALWAYS call the tool again to get current data.
- Dashboard data changes in real-time; previous tool results are immediately stale.

**Task Management Workflow:**

1. **ALWAYS** pass these system parameters to every tool:
   - 'current_user_id': '{user_id}'
   - 'company_id': '{company_id}'

2. **Creating Tasks:**
   - Required: Title, Due Date (YYYY-MM-DD), Assignee Name
   - Optional: Description, Priority (Low/Medium/High), Project Name
   - Use 'list_users' to find available users by name
   - Use 'list_projects' to find available projects by name
   - Users cannot assign tasks to themselves

3. **Viewing Tasks:**
   - Use 'view_my_tasks' to see ONLY tasks ASSIGNED to you (where you are the assignee)
   - Use 'view_all_my_tasks' when asked about "all tasks", "my work", "my tasks" - shows BOTH assigned to you AND created by you
   - Use 'search_user_tasks' when asked about a specific person's tasks BY NAME (e.g., "show Samriddhi's tasks") - PREFERRED METHOD
   - Use 'view_user_tasks' to see tasks by user NAME (ADMIN ONLY)
   - Use 'view_all_company_tasks' to see ALL tasks in the company (ADMIN ONLY)
   - Use 'get_task_stats' for a summary overview
   - **IMPORTANT:** When asked about another user's tasks by name (e.g., "show Samriddhi's tasks", "what is John working on?"), USE 'search_user_tasks' DIRECTLY with the name!

4. **Updating Tasks:**
   - Use 'update_task_status' with the TASK TITLE to change status (To Do, In Progress, Review, Done)
   - Use 'update_task_priority' with the TASK TITLE to change priority (Low, Medium, High)
   - Use 'update_task_project' with the TASK TITLE and PROJECT NAME to link/change/remove the project association
   - Use the task's title/name from 'view_my_tasks' or other viewing tools

5. **Deleting Tasks:**
   - Use 'delete_task' with the TASK TITLE - only creators can delete their tasks
   - Use the task's title/name from task viewing tools

6. **Getting Task Details:**
   - Use 'get_task_collaborators' to see who is working on a task
   - Use 'get_task_history' to see all changes and activity on a task
   - Use 'get_task_comments' to see the latest 5 comments on a task

**Task Display Format:**
When displaying tasks, use a clean card-style format with emojis for better readability:

📋 **[Task Title]**
┣ Status: `<status>`
┣ Priority: `<priority>`
┣ Due: `<date>`
┣ Assignee: <name>
┣ Collaborators: <names or "None">
┣ Created By: <name>
┗ 🗂️ Project: <project name or "Unassigned">

Add a horizontal separator (---) between tasks for clarity. also Leave a blank line between tasks.
For multiple tasks, add a summary header like "📊 **Found X tasks:**" at the top.

When asked about task details, always show collaborators information directly without needing a separate query.
When displaying collaborators, format as: "Collaborators: Name1, Name2, Name3" or "Collaborators: None"

**Handling Task Details:**
- When users ask about task history, use 'get_task_history' tool
- When users ask about task comments, use 'get_task_comments' tool
- When users ask who is working on a task, use 'get_task_collaborators' tool
- Example user queries: "show task history for X", "get comments on X", "who's working on X", "task collaborators", etc.

**Project Display Format:**
When displaying projects, use a clean format:

🗂️ **[Project Name]**
┣ Client: <client name>
┗ Status: `<status>`

also Add a horizontal separator (---) between projects for clarity. also Leave a blank line between projects.

---

**Important Rules:**
- NEVER show or mention IDs to users - use names and titles instead
- Use task titles to update or delete tasks
- Use user names to assign tasks or view their tasks
- Use project names when associating tasks with projects
- If required fields are missing, ask for them before proceeding
- **ALWAYS call tools to fetch data - NEVER reference old data from this conversation**
- **Treat every data request as if it's the first time - call the tool again**
- **When asked about another user's tasks BY NAME, use 'search_user_tasks' directly - it searches by name!**
- **Admins can view any user's tasks using 'search_user_tasks' or 'view_user_tasks' by name, or all company tasks using 'view_all_company_tasks'**
"""


# --- LangGraph Nodes ---
async def chatbot_node(state: AgentState):
    """Main chatbot node that processes messages."""
    user_id = state.get("user_id", "")
    user_name = state.get("user_name", "User")
    company_id = state.get("company_id", "")
    
    sys_msg = SystemMessage(content=build_system_prompt(user_id, user_name, company_id))
    messages = [sys_msg] + state["messages"]
    response = await llm.ainvoke(messages)
    return {"messages": [response]}


tool_node = ToolNode(tools)


# --- Graph Construction ---
workflow = StateGraph(AgentState)
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("tools", tool_node)


def should_continue(state: AgentState):
    """Decide whether to continue to tools or end."""
    last_message = state["messages"][-1]
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tools"
    return END


workflow.add_edge(START, "chatbot")
workflow.add_conditional_edges("chatbot", should_continue)
workflow.add_edge("tools", "chatbot")

graph_app = workflow.compile()


# ============================================================================
# FastAPI Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - connect/disconnect from database."""
    # Startup
    # Set the main event loop reference for tools to use
    set_main_loop(asyncio.get_running_loop())
    await connect_db()
    yield
    # Shutdown
    await close_db()


api_app = FastAPI(
    title="Dash SaaS Chatbot API",
    description="LangGraph-powered Task Management Chatbot integrated with Dash SaaS",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store
# Format: {user_id: {"messages": [], "user_name": str, "company_id": str, "jwt_token": str}}
sessions: Dict[str, Dict[str, Any]] = {}

# In-memory store for real-time updates
# Format: {user_id: {"task_updates": [], "comment_updates": [], "history_updates": []}}
real_time_updates: Dict[str, Dict[str, list]] = {}


# --- Pydantic Models ---
class ChatRequest(BaseModel):
    """Chat message request."""
    message: str


class ChatResponse(BaseModel):
    """Chat response."""
    response: str
    history: list


class ResetResponse(BaseModel):
    """Reset chat response."""
    status: str
    message: str


class DataChangeNotification(BaseModel):
    """Notification about data changes in the dashboard."""
    changes: list[str]  # List of change descriptions


# --- Authentication Dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Validate JWT token using dash_api's authentication.
    Returns user info extracted from the token.
    """
    # Check if credentials were provided
    if not credentials:
        logger.warning("No credentials provided in request")
        raise HTTPException(
            status_code=401,
            detail="Missing authorization credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Use dash_api's token verification
    payload = dash_verify_token(token, token_type="access")
    if not payload:
        logger.warning(f"Token verification failed")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get full user info from database
    from dash_api.app.models.user import User
    user = await User.get(user_id)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": str(user.id),
        "user_name": user.name,
        "email": user.email,
        "company_id": user.get_effective_company_id(),
        "company_name": user.current_company_name or user.company_name,
        "role": user.role.value if user.role else "Member"
    }


# --- API Endpoints ---

@api_app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Process a chat message and return the AI response.
    Uses the same JWT authentication as the main Dash SaaS API.
    Enables real-time updates via WebSocket.
    """
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]
    jwt_token = credentials.credentials
    
    if not company_id:
        raise HTTPException(
            status_code=400,
            detail="User is not associated with any company"
        )
    
    # Initialize or retrieve session
    if user_id not in sessions:
        sessions[user_id] = {
            "messages": [],
            "user_name": user_name,
            "company_id": company_id,
            "jwt_token": jwt_token
        }
        
        # Initialize WebSocket connection for real-time updates
        try:
            await _init_websocket_handlers(current_user, credentials)
            logger.info(f"Initialized WebSocket connection for user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to initialize WebSocket for user {user_id}: {e}")
    
    session = sessions[user_id]
    
    # Update session with latest company info and token
    session["company_id"] = company_id
    session["user_name"] = user_name
    session["jwt_token"] = jwt_token
    
    # Check if this is a data-related query that needs fresh data reminder
    data_keywords = ['task', 'tasks', 'project', 'projects', 'user', 'users', 'assignee', 
                     'assigned', 'show', 'list', 'view', 'get', 'status', 'my', 'all']
    needs_fresh_data = any(keyword in req.message.lower() for keyword in data_keywords)
    
    # If querying data, inject a system reminder to fetch fresh data
    if needs_fresh_data:
        fresh_data_reminder = AIMessage(content=f"[System: Fetching latest data as of {datetime.utcnow().strftime('%H:%M:%S UTC')}...]")
        # Don't add to session, just use for context
    
    # Add user message
    session["messages"].append(HumanMessage(content=req.message))
    
    # Check for recent real-time updates to add context
    user_updates = real_time_updates.get(user_id, {})
    update_context = ""
    if user_updates.get("history_updates") or user_updates.get("comment_updates") or user_updates.get("task_updates"):
        update_context = "\n\n[Real-time Updates Received]"
        if user_updates.get("history_updates"):
            update_context += f"\n- {len(user_updates.get('history_updates', []))} task history update(s)"
        if user_updates.get("comment_updates"):
            update_context += f"\n- {len(user_updates.get('comment_updates', []))} comment update(s)"
        if user_updates.get("task_updates"):
            update_context += f"\n- {len(user_updates.get('task_updates', []))} task update(s)"
    
    # Prepare state for graph
    current_state = {
        "messages": session["messages"],
        "user_id": user_id,
        "user_name": user_name,
        "company_id": company_id
    }
    
    try:
        # Invoke graph asynchronously to avoid blocking the event loop
        # This allows tools to schedule coroutines back to the main loop
        result = await graph_app.ainvoke(current_state)
        
        # Update session with result
        session["messages"] = result["messages"]
        
        # Get the last AI message
        last_msg = session["messages"][-1]
        response_content = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        # Build history for frontend
        history = [
            {
                "role": "user" if isinstance(m, HumanMessage) else "bot",
                "content": m.content if hasattr(m, 'content') else str(m)
            }
            for m in session["messages"]
            if isinstance(m, (HumanMessage, AIMessage))
        ]
        
        return ChatResponse(response=response_content, history=history)
        
    except Exception as e:
        print(f"Error processing chat: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@api_app.post("/reset_chat", response_model=ResetResponse)
async def reset_chat(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Clear the chat history for the current user."""
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]
    
    # Close WebSocket connection
    close_ws_handler(user_id)
    
    # Reset or initialize session
    sessions[user_id] = {
        "messages": [],
        "user_name": user_name,
        "company_id": company_id
    }
    
    # Clear real-time updates
    real_time_updates[user_id] = {
        "task_updates": [],
        "comment_updates": [],
        "history_updates": []
    }
    
    return ResetResponse(
        status="success",
        message=f"Chat history cleared for {user_name}"
    )


@api_app.get("/chat/history")
async def get_chat_history(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get the current chat history for the user."""
    user_id = current_user["user_id"]
    
    if user_id not in sessions:
        return {"history": []}
    
    session = sessions[user_id]
    history = [
        {
            "role": "user" if isinstance(m, HumanMessage) else "bot",
            "content": m.content if hasattr(m, 'content') else str(m),
            "timestamp": datetime.utcnow().isoformat()
        }
        for m in session["messages"]
        if isinstance(m, (HumanMessage, AIMessage))
    ]
    
    return {"history": history}


@api_app.post("/chat/notify_changes")
async def notify_data_changes(
    notification: DataChangeNotification,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Notify the chatbot about data changes in the dashboard.
    This injects a system context message so the LLM knows data has been updated.
    """
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]
    
    # Initialize session if not exists
    if user_id not in sessions:
        sessions[user_id] = {
            "messages": [],
            "user_name": user_name,
            "company_id": company_id
        }
    
    session = sessions[user_id]
    
    # Format changes for the message
    changes_text = "\n".join([f"• {change}" for change in notification.changes])
    
    # Add an AI message that acknowledges the data update
    update_message = AIMessage(content=f"""🔄 **Dashboard Data Updated**

The following changes have been made in the dashboard:
{changes_text}

I'm now aware of these updates. When you ask about tasks, I'll fetch the latest data from the database to ensure accuracy.""")
    
    session["messages"].append(update_message)
    
    return {
        "status": "success",
        "message": f"Notified chatbot about {len(notification.changes)} change(s)"
    }


# ============================================================================
# Real-Time WebSocket Update Handlers
# ============================================================================

async def _init_websocket_handlers(current_user: Dict[str, Any], credentials: HTTPAuthorizationCredentials):
    """Initialize WebSocket connection for real-time updates."""
    user_id = current_user["user_id"]
    company_id = current_user["company_id"]
    jwt_token = credentials.credentials
    
    # Get or create WebSocket handler
    ws_handler = await get_or_create_ws_handler(
        jwt_token=jwt_token,
        user_id=user_id,
        company_id=company_id,
        api_url="http://localhost:8000"  # Adjust to your API URL
    )
    
    # Wait briefly for connection to establish
    connected = await ws_handler.wait_for_connection(timeout=5)
    if not connected:
        logger.warning(f"WebSocket not connected for user {user_id} after 5 seconds, handlers may not work initially")
    else:
        logger.info(f"WebSocket connected for user {user_id}")
    
    # Register handlers for real-time events (register_handler is NOT async)
    ws_handler.register_handler("TASK_HISTORY_UPDATED", 
        lambda data: _handle_task_history_update(user_id, data))
    ws_handler.register_handler("COMMENT_ADDED", 
        lambda data: _handle_comment_added(user_id, data))
    ws_handler.register_handler("COMMENT_DELETED", 
        lambda data: _handle_comment_deleted(user_id, data))
    ws_handler.register_handler("TASK_UPDATED", 
        lambda data: _handle_task_updated(user_id, data))
    
    return ws_handler


def _handle_task_history_update(user_id: str, data: Dict[str, Any]):
    """Handle task history update event."""
    if user_id not in real_time_updates:
        real_time_updates[user_id] = {"task_updates": [], "comment_updates": [], "history_updates": []}
    
    task_id = data.get("task_id")
    history_entry = data.get("history_entry", {})
    
    update_info = {
        "type": "history",
        "task_id": task_id,
        "action": history_entry.get("action"),
        "field_name": history_entry.get("field_name"),
        "old_value": history_entry.get("old_value"),
        "new_value": history_entry.get("new_value"),
        "user_name": history_entry.get("user_name"),
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat())
    }
    
    real_time_updates[user_id]["history_updates"].append(update_info)
    # Keep only last 20 updates
    real_time_updates[user_id]["history_updates"] = real_time_updates[user_id]["history_updates"][-20:]
    
    logger.info(f"Task history update for user {user_id}: task={task_id}, action={history_entry.get('action')}")


def _handle_comment_added(user_id: str, data: Dict[str, Any]):
    """Handle comment added event."""
    if user_id not in real_time_updates:
        real_time_updates[user_id] = {"task_updates": [], "comment_updates": [], "history_updates": []}
    
    task_id = data.get("task_id")
    comment = data.get("comment", {})
    
    update_info = {
        "type": "comment",
        "task_id": task_id,
        "content": comment.get("content"),
        "user_name": comment.get("user_name"),
        "created_at": comment.get("created_at"),
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat())
    }
    
    real_time_updates[user_id]["comment_updates"].append(update_info)
    # Keep only last 20 updates
    real_time_updates[user_id]["comment_updates"] = real_time_updates[user_id]["comment_updates"][-20:]
    
    logger.info(f"Comment added for user {user_id}: task={task_id}, user={comment.get('user_name')}")


def _handle_comment_deleted(user_id: str, data: Dict[str, Any]):
    """Handle comment deleted event."""
    if user_id not in real_time_updates:
        real_time_updates[user_id] = {"task_updates": [], "comment_updates": [], "history_updates": []}
    
    task_id = data.get("task_id")
    comment_id = data.get("comment_id")
    
    update_info = {
        "type": "comment_deleted",
        "task_id": task_id,
        "comment_id": comment_id,
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat())
    }
    
    real_time_updates[user_id]["comment_updates"].append(update_info)
    
    logger.info(f"Comment deleted for user {user_id}: task={task_id}, comment={comment_id}")


def _handle_task_updated(user_id: str, data: Dict[str, Any]):
    """Handle task updated event."""
    if user_id not in real_time_updates:
        real_time_updates[user_id] = {"task_updates": [], "comment_updates": [], "history_updates": []}
    
    task = data.get("task", {})
    
    update_info = {
        "type": "task_updated",
        "task_id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "timestamp": data.get("timestamp", datetime.utcnow().isoformat())
    }
    
    real_time_updates[user_id]["task_updates"].append(update_info)
    # Keep only last 20 updates
    real_time_updates[user_id]["task_updates"] = real_time_updates[user_id]["task_updates"][-20:]
    
    logger.info(f"Task updated for user {user_id}: task={task.get('id')}, status={task.get('status')}")


@api_app.post("/chat/init_realtime")
async def init_realtime_updates(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Initialize real-time WebSocket connection for the user.
    Call this once when the chatbot starts to enable real-time updates.
    """
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    
    try:
        ws_handler = await _init_websocket_handlers(current_user, credentials)
        return {
            "status": "success",
            "message": f"Real-time updates initialized for {user_name}",
            "user_id": user_id,
            "connected": ws_handler.is_connected
        }
    except Exception as e:
        logger.error(f"Error initializing real-time updates: {e}")
        raise HTTPException(status_code=500, detail=f"Error initializing real-time updates: {str(e)}")


@api_app.get("/chat/realtime_updates")
async def get_realtime_updates(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get accumulated real-time updates for the user."""
    user_id = current_user["user_id"]
    
    updates = real_time_updates.get(user_id, {
        "task_updates": [],
        "comment_updates": [],
        "history_updates": []
    })
    
    return {
        "updates": updates,
        "count": len(updates.get("history_updates", [])) + len(updates.get("comment_updates", [])) + len(updates.get("task_updates", []))
    }


@api_app.post("/chat/clear_realtime_updates")
async def clear_realtime_updates(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Clear accumulated real-time updates for the user."""
    user_id = current_user["user_id"]
    
    real_time_updates[user_id] = {
        "task_updates": [],
        "comment_updates": [],
        "history_updates": []
    }
    
    return {"status": "success", "message": "Real-time updates cleared"}


@api_app.get("/chat/ws_status")
async def get_websocket_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get WebSocket connection status."""
    user_id = current_user["user_id"]
    ws_handler = get_ws_handler(user_id)
    
    if not ws_handler:
        return {
            "user_id": user_id,
            "connected": False,
            "message": "No WebSocket connection initialized"
        }
    
    return {
        "user_id": user_id,
        "connected": ws_handler.is_connected,
        "task_histories_cached": len(ws_handler.cached_task_histories),
        "task_comments_cached": len(ws_handler.cached_task_comments),
        "reconnect_attempts": ws_handler.reconnect_attempts,
        "message": "WebSocket connection active" if ws_handler.is_connected else "WebSocket connection inactive"
    }


@api_app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "dash-saas-chatbot",
        "version": "2.0.0",
        "database": "dash_saas"
    }


@api_app.get("/me")
async def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current user info (for testing auth)."""
    return current_user


if __name__ == "__main__":
    # Run the FastAPI application
    uvicorn.run(api_app, host="0.0.0.0", port=8080, reload=True)
