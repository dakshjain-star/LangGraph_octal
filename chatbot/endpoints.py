"""FastAPI endpoints for the chatbot, assembled from original `main.py`."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .app_setup import graph_app, sessions, real_time_updates
from .auth import get_current_user, security
from .realtime import _init_websocket_handlers

from model import connect_db, close_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - connect/disconnect from database."""
    # Startup
    # Set the main event loop reference for tools to use
    from chatbot_tools import set_main_loop
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
# Note: When allow_credentials=True, you cannot use allow_origins=["*"]
# Must specify explicit origins for credentials to work
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://nexus-esw7.onrender.com",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    history: list


class ResetResponse(BaseModel):
    status: str
    message: str


class DataChangeNotification(BaseModel):
    changes: list[str]


@api_app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    credentials = Depends(security),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]
    jwt_token = credentials.credentials

    if not company_id:
        raise HTTPException(status_code=400, detail="User is not associated with any company")

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

    if needs_fresh_data:
        fresh_data_reminder = "[System: Fetching latest data as of %s...]" % datetime.utcnow().strftime('%H:%M:%S UTC')

    # Add user message
    from langchain_core.messages import HumanMessage, AIMessage
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
        logger.exception(f"Error processing chat: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")


@api_app.post("/reset_chat", response_model=ResetResponse)
async def reset_chat(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]

    # Close WebSocket connection
    from websocket_client import close_ws_handler
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
    current_user: Dict[str, Any] = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    user_id = current_user["user_id"]

    from langchain_core.messages import HumanMessage, AIMessage

    chat_history = []
    if user_id in sessions:
        session = sessions[user_id]
        chat_history = [
            {
                "role": "user" if isinstance(m, HumanMessage) else "bot",
                "content": m.content if hasattr(m, 'content') else str(m),
                "timestamp": datetime.utcnow().isoformat(),
                "type": "chat"
            }
            for m in session["messages"]
            if isinstance(m, (HumanMessage, AIMessage))
        ]

    return {
        "history": chat_history,
        "total": len(chat_history),
        "skip": skip,
        "limit": limit
    }


@api_app.get("/chat/task_history")
async def get_task_history(
    current_user: Dict[str, Any] = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    company_id = current_user["company_id"]

    task_history = []
    try:
        from dash_api.app.models.task_history import TaskHistory

        logger.info(f"Fetching task history for company_id: {company_id}, skip: {skip}, limit: {limit}")

        task_history_records = await TaskHistory.find(
            {"company_id": company_id}
        ).sort([("created_at", -1)]).skip(skip).limit(limit).to_list()

        logger.info(f"Found {len(task_history_records)} task history records")

        task_history = []
        for record in task_history_records:
            try:
                action_value = record.action.value if hasattr(record.action, 'value') else str(record.action)
                history_item = {
                    "id": str(record.id),
                    "task_id": record.task_id,
                    "action": action_value,
                    "field_name": record.field_name,
                    "old_value": record.old_value,
                    "new_value": record.new_value,
                    "user_name": record.user_name,
                    "user_avatar": record.user_avatar,
                    "timestamp": record.created_at.isoformat() if record.created_at else datetime.utcnow().isoformat(),
                    "type": "task_history"
                }
                task_history.append(history_item)
            except Exception as record_error:
                logger.error(f"Error processing task history record: {record_error}")
                continue

        logger.info(f"Successfully processed {len(task_history)} task history items")

    except Exception as e:
        logger.error(f"Error fetching task history: {e}", exc_info=True)
        task_history = []

    return {
        "history": task_history,
        "total": len(task_history),
        "skip": skip,
        "limit": limit
    }


@api_app.get("/chat/history/debug")
async def debug_task_history(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    company_id = current_user["company_id"]

    try:
        from dash_api.app.models.task_history import TaskHistory

        logger.info(f"DEBUG: Checking task history for company_id: {company_id}")

        all_records = await TaskHistory.find().to_list()
        logger.info(f"DEBUG: Total task history records in DB: {len(all_records)}")

        company_records = await TaskHistory.find({"company_id": company_id}).to_list()
        logger.info(f"DEBUG: Task history records for this company: {len(company_records)}")

        if company_records:
            sample = company_records[0]
            logger.info(f"DEBUG: Sample record: task_id={sample.task_id}, action={sample.action}, company_id={sample.company_id}")

        return {
            "total_in_db": len(all_records),
            "for_company": len(company_records),
            "company_id": company_id,
            "sample": {
                "task_id": company_records[0].task_id if company_records else None,
                "action": str(company_records[0].action) if company_records else None,
                "created_at": company_records[0].created_at.isoformat() if company_records else None
            } if company_records else None
        }
    except Exception as e:
        logger.error(f"DEBUG Error: {e}", exc_info=True)
        return {"error": str(e)}


@api_app.post("/chat/notify_changes")
async def notify_data_changes(
    notification: DataChangeNotification,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    user_name = current_user["user_name"]
    company_id = current_user["company_id"]

    if user_id not in sessions:
        sessions[user_id] = {
            "messages": [],
            "user_name": user_name,
            "company_id": company_id
        }

    session = sessions[user_id]

    changes_text = "\n".join([f"• {change}" for change in notification.changes])

    from langchain_core.messages import AIMessage
    update_message = AIMessage(content=f"""🔄 **Dashboard Data Updated**

The following changes have been made in the dashboard:
{changes_text}

I'm now aware of these updates. When you ask about tasks, I'll fetch the latest data from the database to ensure accuracy.""")

    session["messages"].append(update_message)

    return {
        "status": "success",
        "message": f"Notified chatbot about {len(notification.changes)} change(s)"
    }


# Real-time endpoints
@api_app.post("/chat/init_realtime")
async def init_realtime_updates(
    credentials = Depends(security),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
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
    user_id = current_user["user_id"]
    from websocket_client import get_ws_handler

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


@api_app.post("/chat/test_notification")
async def test_chatbot_notification(
    credentials = Depends(security)
):
    try:
        from dash_api.app.services.websocket import notify_chatbot_db_change, manager

        company_id = None
        user_id = None

        if credentials and getattr(credentials, 'credentials', None):
            try:
                from dash_api.app.services.auth import verify_token as dash_verify_token
                payload = dash_verify_token(credentials.credentials, token_type="access")
                if payload:
                    user_id = payload.get("sub")
                    from dash_api.app.models.user import User
                    user = await User.get(user_id)
                    if user:
                        company_id = user.current_company_id or (user.company_ids[0] if user.company_ids else None)
            except Exception:
                pass

        if not company_id:
            active_companies = list(manager.company_users.keys())
            logger.info(f"[TEST] No specific company, broadcasting to all: {active_companies}")

            for comp_id in active_companies:
                await notify_chatbot_db_change(
                    comp_id,
                    "test_notification",
                    {
                        "test": True,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message": "Test notification from chatbot"
                    }
                )

            return {
                "status": "success",
                "message": f"Test notification sent to {len(active_companies)} company/companies",
                "companies": active_companies
            }

        logger.info(f"[TEST] Triggering notification for company {company_id}")

        await notify_chatbot_db_change(
            company_id,
            "test_notification",
            {
                "test": True,
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Test notification from chatbot"
            }
        )

        return {
            "status": "success",
            "message": "Test notification sent",
            "company_id": company_id,
            "user_id": user_id
        }
    except Exception as e:
        logger.error(f"[TEST] Failed to send notification: {e}")
        import traceback
        logger.error(f"[TEST] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@api_app.get("/health")
async def health():
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
    return current_user


if __name__ == "__main__":
    uvicorn.run(api_app, host="0.0.0.0", port=8081, reload=True)
