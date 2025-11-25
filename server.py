from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
import bcrypt
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
# Format: {user_id: {"messages": [], "user_name": str}}
sessions: Dict[str, Dict[str, Any]] = {}

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    message: str
    user_id: str


class ResetChatRequest(BaseModel):
    user_id: str

@app.post("/login")
def login(req: LoginRequest):
    user = db.users.find_one({"email": req.email})
    if user and bcrypt.checkpw(req.password.encode('utf-8'), user['password']):
        user_id = str(user["_id"])
        # Initialize session if not exists
        if user_id not in sessions:
            sessions[user_id] = {
                "messages": [],
                "user_id": user_id,
                "user_name": user["first_name"]
            }
        
        return {
            "user_id": user_id,
            "user_name": user["first_name"],
            "status": "success"
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/chat")
def chat(req: ChatRequest):
    user_id = req.user_id
    if user_id not in sessions:
        # Try to recover session if user exists in DB but server restarted
        # For now, just re-init empty session or fail
        # Let's re-init for robustness if we trust the ID (in real app, verify token)
        sessions[user_id] = {
            "messages": [],
            "user_id": user_id,
            "user_name": "User"
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
    user_id = req.user_id
    if user_id in sessions:
        user_name = sessions[user_id].get("user_name", "User")
        sessions[user_id] = {
            "messages": [],
            "user_id": user_id,
            "user_name": user_name,
        }
        return {"status": "success"}
    # If session doesn't exist, treat as success so UI stays simple
    return {"status": "success"}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # Run the FastAPI application (not the LangGraph compiled app)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
