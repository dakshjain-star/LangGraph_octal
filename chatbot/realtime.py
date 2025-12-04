"""Real-time WebSocket update handlers for chatbot."""
from datetime import datetime
from typing import Dict, Any
import logging

from websocket_client import get_or_create_ws_handler, get_ws_handler, close_ws_handler
from .app_setup import real_time_updates

logger = logging.getLogger(__name__)


async def _init_websocket_handlers(current_user: Dict[str, Any], credentials):
    """Initialize WebSocket connection for real-time updates."""
    user_id = current_user["user_id"]
    company_id = current_user["company_id"]
    jwt_token = credentials.credentials

    # Get or create WebSocket handler
    ws_handler = await get_or_create_ws_handler(
        jwt_token=jwt_token,
        user_id=user_id,
        company_id=company_id,
        api_url="https://nexus-backend-g0gm.onrender.com"
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
