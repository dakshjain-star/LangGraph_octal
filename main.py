"""
LangGraph Task Management Chatbot - Integrated with dash_saas.
Uses the same JWT authentication and database as the main dashboard API.
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

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*Pydantic V1.*")

# Security
security = HTTPBearer()


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

    return f"""
{random.choice(assistant_roles)}

**Current User Context:**
- User ID: {user_id}
- User Name: {display_name}
- Company ID: {company_id}

**General Behavior:**
- Be helpful, friendly, and concise in your responses.
- When users greet you, respond warmly with "Hello {display_name}!" and offer assistance.
- When users say thank you, respond politely and ask if they need anything else.

**Task Management Workflow:**

1. **ALWAYS** pass these system parameters to every tool:
   - 'current_user_id': '{user_id}'
   - 'company_id': '{company_id}'

2. **Creating Tasks:**
   - Required: Title, Due Date (YYYY-MM-DD), Assignee ID
   - Optional: Description, Priority (Low/Medium/High), Project ID
   - FIRST use 'list_users' to get assignable user IDs
   - Optionally use 'list_projects' to get project IDs
   - Users cannot assign tasks to themselves

3. **Viewing Tasks:**
   - Use 'view_my_tasks' to see tasks assigned to or created by the user
   - Use 'get_task_stats' for a summary overview

4. **Updating Tasks:**
   - Use 'update_task_status' to change status (To Do, In Progress, Review, Done)
   - Use 'update_task_priority' to change priority (Low, Medium, High)
   - Get task IDs from 'view_my_tasks' first

5. **Deleting Tasks:**
   - Use 'delete_task' - only creators can delete their tasks
   - Get task IDs from 'view_my_tasks' first

**Task Display Format:**
Present task lists as bulleted items:
* **Task Title** (ID: <id>)
  * **Status:** <status>
  * **Priority:** <priority>
  * **Due Date:** <date>
  * **Assignee:** <name>
  * **Created By:** <name>
  * **Project:** <project name or "No project">

**Important Rules:**
- Never fabricate task IDs; use only IDs from 'view_my_tasks'
- If required fields are missing, ask for them before proceeding
- When showing users for assignment, include their IDs for easy reference
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
# Format: {user_id: {"messages": [], "user_name": str, "company_id": str}}
sessions: Dict[str, Dict[str, Any]] = {}


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


# --- Authentication Dependency ---
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """
    Validate JWT token using dash_api's authentication.
    Returns user info extracted from the token.
    """
    token = credentials.credentials
    
    # Use dash_api's token verification
    payload = dash_verify_token(token, token_type="access")
    if not payload:
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
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Process a chat message and return the AI response.
    Uses the same JWT authentication as the main Dash SaaS API.
    """
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]
    
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
            "company_id": company_id
        }
    
    session = sessions[user_id]
    
    # Update session with latest company info
    session["company_id"] = company_id
    session["user_name"] = user_name
    
    # Add user message
    session["messages"].append(HumanMessage(content=req.message))
    
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
    
    # Reset or initialize session
    sessions[user_id] = {
        "messages": [],
        "user_name": user_name,
        "company_id": company_id
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
