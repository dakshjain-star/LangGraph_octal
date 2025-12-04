"""WebSocket connection manager for real-time updates."""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set, Any
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Supports:
    - User-specific connections (for task/project assignments)
    - Company-wide broadcasts (for team updates)
    - Multiple connections per user (multiple tabs/devices)
    """
    
    def __init__(self):
        # Map user_id to their WebSocket connections
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # Map company_id to user_ids for company broadcasts
        self.company_users: Dict[str, Set[str]] = {}
        # Track which company each user belongs to
        self.user_company_map: Dict[str, str] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str, company_id: str = None):
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            user_id: The user's ID
            company_id: Optional company ID for company-wide broadcasts
        """
        await websocket.accept()
        
        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)
        
        # Track company membership
        if company_id:
            self.user_company_map[user_id] = company_id
            if company_id not in self.company_users:
                self.company_users[company_id] = set()
            self.company_users[company_id].add(user_id)
        
        logger.info(f"WebSocket connected: user={user_id}, company={company_id}, total_connections={self.total_connections}")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: The WebSocket connection to remove
            user_id: The user's ID
        """
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            
            # Clean up empty sets
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
                
                # Remove from company tracking
                company_id = self.user_company_map.pop(user_id, None)
                if company_id and company_id in self.company_users:
                    self.company_users[company_id].discard(user_id)
                    if not self.company_users[company_id]:
                        del self.company_users[company_id]
        
        logger.info(f"WebSocket disconnected: user={user_id}, total_connections={self.total_connections}")
    
    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return sum(len(connections) for connections in self.user_connections.values())
    
    def is_user_online(self, user_id: str) -> bool:
        """Check if a user has any active connections."""
        return user_id in self.user_connections and len(self.user_connections[user_id]) > 0
    
    async def send_to_user(self, user_id: str, message: dict):
        """
        Send a message to a specific user (all their connections).
        
        Args:
            user_id: The user's ID
            message: The message to send (will be JSON serialized)
        """
        if user_id in self.user_connections:
            # Add timestamp to message
            message["timestamp"] = datetime.utcnow().isoformat()
            
            dead_connections = set()
            for connection in self.user_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")
                    dead_connections.add(connection)
            
            # Clean up dead connections
            for dead in dead_connections:
                self.user_connections[user_id].discard(dead)
    
    async def send_to_users(self, user_ids: list, message: dict):
        """
        Send a message to multiple users.
        
        Args:
            user_ids: List of user IDs
            message: The message to send
        """
        for user_id in user_ids:
            await self.send_to_user(user_id, message)
    
    async def broadcast_to_company(self, company_id: str, message: dict, exclude_user: str = None):
        """
        Broadcast a message to all users in a company.
        
        Args:
            company_id: The company ID
            message: The message to send
            exclude_user: Optional user ID to exclude from broadcast (e.g., the sender)
        """
        if company_id in self.company_users:
            for user_id in self.company_users[company_id]:
                if user_id != exclude_user:
                    await self.send_to_user(user_id, message)
    
    async def broadcast_all(self, message: dict):
        """
        Broadcast a message to all connected users.
        
        Args:
            message: The message to send
        """
        for user_id in list(self.user_connections.keys()):
            await self.send_to_user(user_id, message)


# Global connection manager instance
manager = ConnectionManager()


# Event types for real-time updates
class WebSocketEventType:
    """WebSocket event type constants."""
    # Task events
    TASK_CREATED = "TASK_CREATED"
    TASK_UPDATED = "TASK_UPDATED"
    TASK_DELETED = "TASK_DELETED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_UNASSIGNED = "TASK_UNASSIGNED"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    
    # Project events
    PROJECT_CREATED = "PROJECT_CREATED"
    PROJECT_UPDATED = "PROJECT_UPDATED"
    PROJECT_DELETED = "PROJECT_DELETED"
    PROJECT_MEMBER_ADDED = "PROJECT_MEMBER_ADDED"
    
    # User events
    USER_INVITED = "USER_INVITED"
    USER_JOINED = "USER_JOINED"
    USER_UPDATED = "USER_UPDATED"
    USER_PROFILE_UPDATED = "USER_PROFILE_UPDATED"
    
    # Comment events
    COMMENT_ADDED = "COMMENT_ADDED"
    COMMENT_DELETED = "COMMENT_DELETED"
    
    # Task History events
    TASK_HISTORY_UPDATED = "TASK_HISTORY_UPDATED"
    TASK_COLLABORATORS_UPDATED = "TASK_COLLABORATORS_UPDATED"
    
    # Invitation events
    INVITATION_RECEIVED = "INVITATION_RECEIVED"
    INVITATION_RESPONSE = "INVITATION_RESPONSE"
    
    # Notification events
    NOTIFICATION = "NOTIFICATION"
    
    # Chatbot events
    CHATBOT_DB_CHANGE = "CHATBOT_DB_CHANGE"
    
    # System events
    CONNECTION_ESTABLISHED = "CONNECTION_ESTABLISHED"
    PING = "PING"
    PONG = "PONG"


async def notify_task_created(task_data: dict, company_id: str, creator_id: str = None):
    """Notify relevant users when a task is created."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.TASK_CREATED,
            "payload": task_data
        }
    )


async def notify_task_updated(task_data: dict, company_id: str, updater_id: str = None):
    """Notify relevant users when a task is updated."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.TASK_UPDATED,
            "payload": task_data
        }
    )


async def notify_task_assigned(task_data: dict, assignee_id: str, assigner_id: str = None):
    """Notify a user when a task is assigned to them."""
    # Send to the assignee specifically
    await manager.send_to_user(
        assignee_id,
        {
            "type": WebSocketEventType.TASK_ASSIGNED,
            "payload": {
                **task_data,
                "message": f"A new task '{task_data.get('title', 'Unknown')}' has been assigned to you"
            }
        }
    )


async def notify_task_unassigned(task_data: dict, old_assignee_id: str, assigner_id: str = None):
    """Notify a user when a task is unassigned from them (reassigned to someone else)."""
    # Send to the old assignee specifically
    await manager.send_to_user(
        old_assignee_id,
        {
            "type": WebSocketEventType.TASK_UNASSIGNED,
            "payload": {
                **task_data,
                "message": f"Task '{task_data.get('title', 'Unknown')}' has been reassigned to another user"
            }
        }
    )


async def notify_task_deleted(task_id: str, company_id: str, deleter_id: str = None):
    """Notify relevant users when a task is deleted."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.TASK_DELETED,
            "payload": {"task_id": task_id}
        }
    )


async def notify_task_history_updated(task_id: str, history_data: dict, company_id: str):
    """Notify relevant users when task history is updated."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.TASK_HISTORY_UPDATED,
            "payload": {
                "task_id": task_id,
                "history_entry": history_data
            }
        }
    )


async def notify_task_collaborators_updated(task_id: str, collaborators_data: dict, company_id: str, updater_id: str = None):
    """Notify relevant users when task collaborators are updated."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.TASK_COLLABORATORS_UPDATED,
            "payload": {
                "task_id": task_id,
                "collaborators": collaborators_data
            }
        }
    )


async def notify_project_created(project_data: dict, company_id: str, creator_id: str = None):
    """Notify relevant users when a project is created."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.PROJECT_CREATED,
            "payload": project_data
        }
    )


async def notify_project_updated(project_data: dict, company_id: str, updater_id: str = None):
    """Notify relevant users when a project is updated."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.PROJECT_UPDATED,
            "payload": project_data
        }
    )


async def notify_project_deleted(project_id: str, company_id: str, deleter_id: str = None):
    """Notify relevant users when a project is deleted."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.PROJECT_DELETED,
            "payload": {"project_id": project_id}
        }
    )


async def notify_user_invited(invitation_data: dict, invitee_user_id: str):
    """Notify a user when they receive an invitation."""
    await manager.send_to_user(
        invitee_user_id,
        {
            "type": WebSocketEventType.USER_INVITED,
            "payload": {
                **invitation_data,
                "message": f"You have been invited to join {invitation_data.get('company_name', 'a company')}"
            }
        }
    )


async def notify_comment_added(comment_data: dict, task_id: str, company_id: str, commenter_id: str = None):
    """Notify relevant users when a comment is added."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.COMMENT_ADDED,
            "payload": {
                **comment_data,
                "task_id": task_id
            }
        }
    )


async def notify_comment_deleted(comment_id: str, task_id: str, company_id: str, deleter_id: str = None):
    """Notify relevant users when a comment is deleted."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.COMMENT_DELETED,
            "payload": {
                "comment_id": comment_id,
                "task_id": task_id
            }
        },
        exclude_user=deleter_id
    )


async def notify_invitation_response(invitation_data: dict, inviter_id: str, action: str):
    """Notify company admin when user responds to invitation."""
    # Use proper past tense for the action
    action_past = "accepted" if action == "accept" else "declined"
    await manager.send_to_user(
        inviter_id,
        {
            "type": WebSocketEventType.INVITATION_RESPONSE,
            "payload": {
                **invitation_data,
                "action": action,
                "message": f"{invitation_data.get('invitee_email', 'User')} has {action_past} your invitation"
            }
        }
    )


async def notify_user_joined(user_data: dict, company_id: str):
    """Notify all users in a company when a new user joins."""
    await manager.broadcast_to_company(
        company_id,
        {
            "type": WebSocketEventType.USER_JOINED,
            "payload": {
                **user_data,
                "message": f"{user_data.get('name', 'A new user')} has joined the company"
            }
        }
    )


async def notify_chatbot_db_change(company_id: str, change_type: str, details: dict = None):
    """Notify all users in a company when chatbot makes a database change."""
    logger.info(f"[CHATBOT] Notifying company {company_id} about DB change: {change_type}")
    logger.info(f"[CHATBOT] Change details: {details}")
    
    message = {
        "type": WebSocketEventType.CHATBOT_DB_CHANGE,
        "payload": {
            "change_type": change_type,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Chatbot made a change: {change_type}"
        }
    }
    
    logger.info(f"[CHATBOT] Broadcasting message: {message}")
    logger.info(f"[CHATBOT] Company users: {manager.company_users.get(company_id, set())}")
    
    await manager.broadcast_to_company(
        company_id,
        message
    )
    
    logger.info(f"[CHATBOT] Notification sent successfully for {change_type}")


async def notify_user_profile_updated(user_data: dict, company_id: str):
    """Notify all users in a company when a user's profile is updated."""
    logger.info(f"[PROFILE] Notifying company {company_id} about user profile update: {user_data.get('id')}")
    
    # Serialize datetime objects for JSON
    serialized_data = {}
    for key, value in user_data.items():
        if hasattr(value, 'isoformat'):
            serialized_data[key] = value.isoformat()
        elif hasattr(value, 'value'):  # Enum
            serialized_data[key] = value.value
        else:
            serialized_data[key] = value
    
    message = {
        "type": WebSocketEventType.USER_PROFILE_UPDATED,
        "payload": {
            **serialized_data,
            "message": f"User {user_data.get('name', 'Unknown')} updated their profile"
        }
    }
    
    await manager.broadcast_to_company(
        company_id,
        message
    )
    
    logger.info(f"[PROFILE] User profile update notification sent for user {user_data.get('id')}")
