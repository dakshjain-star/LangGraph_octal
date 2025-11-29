"""WebSocket routes for real-time communication."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
from typing import Optional
import logging
import json

from app.services.websocket import manager, WebSocketEventType
from app.models.user import User
from app.middleware.auth import get_current_user_optional

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_user_from_token(token: str) -> Optional[User]:
    """Validate token and get user for WebSocket connection."""
    if not token:
        return None
    
    try:
        from jose import jwt, JWTError
        from app.config import settings
        
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        user = await User.get(user_id)
        return user
    except JWTError as e:
        logger.warning(f"WebSocket token validation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error validating WebSocket token: {e}")
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None, description="JWT access token")
):
    """
    WebSocket endpoint for real-time updates.
    
    Connect with: ws://localhost:8000/api/v1/ws?token=<your_jwt_token>
    
    Events you'll receive:
    - TASK_CREATED: When a new task is created in your company
    - TASK_UPDATED: When a task is updated
    - TASK_ASSIGNED: When a task is assigned to you
    - TASK_DELETED: When a task is deleted
    - PROJECT_CREATED: When a new project is created
    - PROJECT_UPDATED: When a project is updated
    - PROJECT_DELETED: When a project is deleted
    - COMMENT_ADDED: When a comment is added to a task
    - NOTIFICATION: General notifications
    
    You can send:
    - {"type": "PING"}: Server will respond with PONG
    """
    # Validate token and get user
    user = await get_user_from_token(token)
    
    if not user:
        await websocket.close(code=4001, reason="Invalid or missing token")
        return
    
    user_id = str(user.id)
    company_id = user.get_effective_company_id()
    
    # Connect
    await manager.connect(websocket, user_id, company_id)
    
    # Send connection confirmation
    await websocket.send_json({
        "type": WebSocketEventType.CONNECTION_ESTABLISHED,
        "payload": {
            "user_id": user_id,
            "company_id": company_id,
            "message": "Connected to real-time updates"
        }
    })
    
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Handle ping/pong for keepalive
                if message_type == WebSocketEventType.PING:
                    await websocket.send_json({
                        "type": WebSocketEventType.PONG,
                        "payload": {"status": "alive"}
                    })
                else:
                    # Echo back unknown messages for debugging
                    logger.debug(f"Received message from {user_id}: {message}")
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from user {user_id}: {data}")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        logger.info(f"User {user_id} disconnected from WebSocket")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(websocket, user_id)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection statistics."""
    return {
        "total_connections": manager.total_connections,
        "total_users_online": len(manager.user_connections),
        "companies_with_users": len(manager.company_users)
    }
