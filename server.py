from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import bcrypt
import uuid
import secrets
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, AIMessage
from main import app as graph_app, db

app = FastAPI()

# Enable CORS
app.add_middleware(
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

@app.post("/login")
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

@app.post("/chat")
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


@app.post("/reset_chat")
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

@app.post("/verify_token")
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


@app.post("/logout")
def logout(req: VerifyTokenRequest):
    """Logout by invalidating the token."""
    if req.token in token_store:
        del token_store[req.token]
    return {"status": "success"}


@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the FastAPI application (not the LangGraph compiled app)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
