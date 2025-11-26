import os
import random
from typing import Annotated, List, Optional, Dict, Any
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage, AIMessage
from langchain_ollama import ChatOllama
from bson.objectid import ObjectId
import bcrypt
import warnings
import json
from datetime import datetime, timedelta
import secrets
import uvicorn
from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import from new modules
from model import db
from tools import tools

warnings.filterwarnings("ignore", category=UserWarning, module="langchain_core")
warnings.filterwarnings("ignore", message=".*Pydantic V1.*")

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: Optional[str]
    user_name: Optional[str]

# --- INITIALIZE OLLAMA ---
# We use the specific model you requested.
# ensure "ollama serve" is running in your terminal.

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


def build_system_prompt(user_id: Optional[str], user_name: Optional[str]) -> str:
    """Create a dynamic MongoDB-only system prompt with rotating guidance."""
    mongo_roles = [
        "Act as a MongoDB-only assistant focused on data modeling, Atlas collections, and CRUD workflows.",
        "You are a MongoDB CRUD co-pilot dedicated exclusively to database records, documents, and query operations.",
        "Serve as a MongoDB data concierge who only reasons about collections, documents, indexes, and CRUD lifecycles."
    ]
    refusal_lines = [
        "Politely refuse any request that is not about MongoDB data access, modeling, or CRUD operations and redirect the user back to those topics.",
        "Decline every non-MongoDB topic with a short reminder that you only operate on MongoDB data and CRUD actions.",
        "If the conversation drifts away from MongoDB CRUD or data-centric needs, immediately refuse and restate the MongoDB-only charter."
    ]
    greeting_rules = [
        "Detect greetings (hi, hello, hey, morning, evening, namaste, etc.) and respond starting with 'Hello {display_name}' followed by a MongoDB-only reminder.",
        "Whenever the user greets you, lead with 'Hello {display_name}' (no self-introduction) and quickly steer the chat toward MongoDB CRUD work.",
        "Respond to any greeting or pleasantry by opening with 'Hello {display_name}' then restating that you only help with MongoDB data, collections, and CRUD questions."
    ]
    courtesy_rules = [
        "If users only greet or thank you, keep the reply short, friendly, and gently steer them toward MongoDB CRUD assistance without mentioning the current time or your own name.",
        "Vary your greeting tone so consecutive salutations feel fresh while still emphasizing the MongoDB-only charter and avoid saying 'I'm <name>'."
    ]

    time_hint = datetime.now().strftime("%A %I:%M %p")
    display_name = user_name or "there"
    greeting_instruction = random.choice(greeting_rules).format(display_name=display_name)
    courtesy_instruction = random.choice(courtesy_rules)

    return f"""
{random.choice(mongo_roles)}
Current User ID: {user_id}.

General Behavior:
- {random.choice(refusal_lines)}
- Never discuss topics outside MongoDB databases, Atlas data, document schemas, aggregation, indexing, or CRUD tooling. If a user goes off-topic, decline and redirect them to MongoDB CRUD needs.
- {greeting_instruction}
- {courtesy_instruction}

Task Workflow Rules:
1. ALWAYS pass '{user_id}' as the 'current_user_id' argument when invoking any tool.
2. Do not fabricate task IDs; use only the IDs returned by the 'view_my_tasks' tool.
3. When creating a task you MUST collect Title, Start Date (YYYY-MM-DD), End Date (YYYY-MM-DD), and Assignee Email. Ask for optional Description and Priority.
4. The 'assigned_by' field is implicitly the current user ({user_id}); never ask the user for it.
5. Call 'list_users' when the user needs available teammates or emails.
6. Present task lists as bulleted items with nested fields exactly like:
   * **Task Title** (ID: <id>)
     * **Description:** <desc>
     * **Priority:** <priority>
     * **Start Date:** <start>
     * **End Date:** <end>
     * **Assigned By:** <full name, email>
     * **Assignee:** <full name, email>
7. If required fields are missing, ask for them before executing 'create_task'.
"""

def chatbot_node(state: AgentState):
    user_id = state["user_id"]
    
    # System prompt is critical for local models to understand they must use the ID
    sys_msg = SystemMessage(content=build_system_prompt(user_id, state.get("user_name")))
    
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

graph_app = workflow.compile()

# ============================================================================
# FastAPI Server
# ============================================================================

api_app = FastAPI()

# Enable CORS
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store
# Format: {user_id: {"messages": [], "user_name": str, "email": str}}
sessions: Dict[str, Dict[str, Any]] = {}

# Token store: {token: {"user_id": str, "email": str, "user_name": str, "expires_at": datetime}}
token_store: Dict[str, Dict[str, Any]] = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    message: str
    token: str

class ResetChatRequest(BaseModel):
    token: str

class VerifyTokenRequest(BaseModel):
    token: str

@api_app.post("/login")
def login(req: LoginRequest):
    user = db.users.find_one({"email": req.email})
    if user and bcrypt.checkpw(req.password.encode('utf-8'), user['password']):
        user_id = str(user["_id"])
        
        # Generate unique session token
        token = secrets.token_urlsafe(32)
        
        # Store token with expiry (30 days)
        token_store[token] = {
            "user_id": user_id,
            "email": req.email,
            "user_name": user["first_name"],
            "expires_at": datetime.now() + timedelta(days=30)
        }
        
        # Initialize or reuse session for this user_id
        if user_id not in sessions:
            sessions[user_id] = {
                "messages": [],
                "user_id": user_id,
                "user_name": user["first_name"],
                "email": req.email
            }
        
        return {
            "token": token,
            "user_id": user_id,
            "user_name": user["first_name"],
            "email": req.email,
            "status": "success"
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")

@api_app.post("/chat")
def chat(req: ChatRequest):
    # Verify token
    if req.token not in token_store:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    token_data = token_store[req.token]
    
    # Check if token has expired
    if token_data["expires_at"] < datetime.now():
        del token_store[req.token]
        raise HTTPException(status_code=401, detail="Token expired")
    
    user_id = token_data["user_id"]
    
    # Initialize session if it doesn't exist (e.g., after server restart)
    if user_id not in sessions:
        sessions[user_id] = {
            "messages": [],
            "user_id": user_id,
            "user_name": token_data["user_name"],
            "email": token_data["email"]
        }
    
    session = sessions[user_id]
    
    # Add user message
    session["messages"].append(HumanMessage(content=req.message))
    
    # Prepare state for graph
    # Note: The graph expects 'messages' in the state
    current_state = {
        "messages": session["messages"],
        "user_id": session["user_id"],
        "user_name": session["user_name"]
    }
    
    try:
        # Invoke graph
        result = graph_app.invoke(current_state)
        
        # Update session history with result
        # The result['messages'] contains the full history including new response
        session["messages"] = result["messages"]
        
        # Get the last message (Bot response)
        last_msg = session["messages"][-1]
        
        return {
            "response": last_msg.content,
            "history": [
                {"role": "user" if isinstance(m, HumanMessage) else "bot", "content": m.content}
                for m in session["messages"]
                if isinstance(m, (HumanMessage, AIMessage))
            ]
        }
    except Exception as e:
        print(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_app.post("/reset_chat")
def reset_chat(req: ResetChatRequest):
    """Clear the in-memory chat history for a given user."""
    # Verify token
    if req.token not in token_store:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    token_data = token_store[req.token]
    user_id = token_data["user_id"]
    
    if user_id in sessions:
        user_name = sessions[user_id].get("user_name", "User")
        email = sessions[user_id].get("email", "")
        sessions[user_id] = {
            "messages": [],
            "user_id": user_id,
            "user_name": user_name,
            "email": email
        }
        return {"status": "success"}
    # If session doesn't exist, treat as success so UI stays simple
    return {"status": "success"}

@api_app.post("/verify_token")
def verify_token(req: VerifyTokenRequest):
    """Verify if a token is valid and return user data."""
    if req.token not in token_store:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    token_data = token_store[req.token]
    
    # Check if token has expired
    if token_data["expires_at"] < datetime.now():
        del token_store[req.token]
        raise HTTPException(status_code=401, detail="Token expired")
    
    return {
        "user_id": token_data["user_id"],
        "user_name": token_data["user_name"],
        "email": token_data["email"],
        "status": "success"
    }


@api_app.post("/logout")
def logout(req: VerifyTokenRequest):
    """Logout by invalidating the token."""
    if req.token in token_store:
        del token_store[req.token]
    return {"status": "success"}


@api_app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the FastAPI application
    uvicorn.run(api_app, host="0.0.0.0", port=8000)