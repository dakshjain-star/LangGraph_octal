"""WebSocket routes for real-time communication."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status, Header
from typing import Optional
from pydantic import BaseModel
import logging
import json

from app.services.websocket import manager, WebSocketEventType, notify_chatbot_db_change, notify_user_invited
from app.models.user import User
from app.middleware.auth import get_current_user_optional
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic model for chatbot notification request
class ChatbotNotificationRequest(BaseModel):
    """Request model for chatbot DB change notification."""
    company_id: str
    change_type: str
    details: dict = {}


# Pydantic model for user invitation notification
class InvitationNotificationRequest(BaseModel):
    """Request model for invitation notification to a specific user."""
    invitee_user_id: str
    invitation_data: dict


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
        "companies_with_users": len(manager.company_users),
        "company_user_map": {k: list(v) for k, v in manager.company_users.items()}
    }


@router.post("/ws/chatbot-notify")
async def chatbot_notify(
    request: ChatbotNotificationRequest,
    x_internal_secret: str = Header(None, alias="X-Internal-Secret")
):
    """
    HTTP endpoint for chatbot to trigger WebSocket notifications.
    
    This endpoint is called by the chatbot (running on port 8080) to notify
    the dash_api (running on port 8000) to broadcast WebSocket messages.
    
    The chatbot and dash_api run in separate processes, so direct function
    calls don't work - we need HTTP communication.
    """
    # Validate internal secret for security (optional but recommended)
    expected_secret = getattr(settings, 'internal_api_secret', 'chatbot-internal-secret')
    if x_internal_secret != expected_secret:
        logger.warning(f"[CHATBOT NOTIFY] Invalid or missing internal secret")
        # For now, allow requests without secret but log warning
        # In production, you should require the secret
    
    logger.info(f"[CHATBOT NOTIFY] Received notification request: company={request.company_id}, type={request.change_type}")
    logger.info(f"[CHATBOT NOTIFY] Details: {request.details}")
    logger.info(f"[CHATBOT NOTIFY] Current company_users: {manager.company_users}")
    
    try:
        await notify_chatbot_db_change(
            company_id=request.company_id,
            change_type=request.change_type,
            details=request.details
        )
        
        return {
            "status": "success",
            "message": f"Notification sent for {request.change_type}",
            "company_id": request.company_id,
            "users_notified": len(manager.company_users.get(request.company_id, set()))
        }
    except Exception as e:
        logger.error(f"[CHATBOT NOTIFY] Failed to send notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ws/invitation-notify")
async def invitation_notify(
    request: InvitationNotificationRequest,
    x_internal_secret: str = Header(None, alias="X-Internal-Secret")
):
    """
    HTTP endpoint for chatbot to send invitation notification to a specific user.
    
    This endpoint sends a USER_INVITED WebSocket event directly to the invitee,
    allowing real-time update when admin sends an invitation via chatbot.
    """
    # Validate internal secret for security
    expected_secret = getattr(settings, 'internal_api_secret', 'chatbot-internal-secret')
    if x_internal_secret != expected_secret:
        logger.warning(f"[INVITATION NOTIFY] Invalid or missing internal secret")
    
    logger.info(f"[INVITATION NOTIFY] Sending invitation notification to user: {request.invitee_user_id}")
    logger.info(f"[INVITATION NOTIFY] Invitation data: {request.invitation_data}")
    
    try:
        await notify_user_invited(request.invitation_data, request.invitee_user_id)
        
        # Check if user is online
        is_online = manager.is_user_online(request.invitee_user_id)
        
        return {
            "status": "success",
            "message": "Invitation notification sent",
            "invitee_user_id": request.invitee_user_id,
            "user_online": is_online
        }
    except Exception as e:
        logger.error(f"[INVITATION NOTIFY] Failed to send notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))
