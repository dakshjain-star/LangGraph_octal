"""
WebSocket client for the chatbot to receive real-time updates.
Connects to the dash_api WebSocket server for task history, comments, and collaborator updates.
"""
import asyncio
import logging
import json
from typing import Callable, Optional, Dict, Any, Set
from datetime import datetime
from urllib.parse import quote
import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


class WebSocketUpdateHandler:
    """Handles real-time WebSocket updates from the API."""
    
    def __init__(self, jwt_token: str, user_id: str, company_id: str, api_url: str = "https://nexus-backend-g0gm.onrender.com"):
        """
        Initialize the WebSocket client handler.
        
        Args:
            jwt_token: JWT token for authentication
            user_id: User ID
            company_id: Company ID
            api_url: Base URL of the API (will be converted to ws:// or wss://)
        """
        self.jwt_token = jwt_token
        self.user_id = user_id
        self.company_id = company_id
        self.api_url = api_url
        self.ws_url = self._build_ws_url(api_url)
        
        # WebSocket connection
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.is_connected = False
        
        # Event handlers
        self.event_handlers: Dict[str, list[Callable]] = {
            "TASK_HISTORY_UPDATED": [],
            "COMMENT_ADDED": [],
            "COMMENT_DELETED": [],
            "TASK_UPDATED": [],
            "TASK_CREATED": [],
            "TASK_DELETED": [],
            "TASK_ASSIGNED": [],
            "USER_UPDATED": [],
            "CHATBOT_DB_CHANGE": [],
        }
        
        # Data cache
        self.cached_task_histories: Dict[str, list] = {}  # task_id -> list of history entries
        self.cached_task_comments: Dict[str, list] = {}   # task_id -> list of comments
        self.cached_task_collaborators: Dict[str, list] = {}  # task_id -> list of collaborators
        
        # Connection state
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2
    
    def _build_ws_url(self, api_url: str) -> str:
        """Convert HTTP URL to WebSocket URL."""
        # Remove trailing slashes
        api_url = api_url.rstrip('/')
        
        if api_url.startswith('https://'):
            ws_url = api_url.replace('https://', 'wss://', 1)
        elif api_url.startswith('http://'):
            ws_url = api_url.replace('http://', 'ws://', 1)
        else:
            ws_url = f"ws://{api_url}"
        
        # URL-encode the JWT token to handle special characters (+, /, =)
        encoded_token = quote(self.jwt_token, safe='')
        return f"{ws_url}/api/v1/ws?token={encoded_token}"
    
    async def wait_for_connection(self, timeout: int = 10) -> bool:
        """Wait for the WebSocket to be connected.
        
        Args:
            timeout: How long to wait in seconds
            
        Returns:
            True if connected, False if timeout
        """
        start_time = datetime.utcnow()
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            if self.is_connected:
                return True
            await asyncio.sleep(0.1)
        
        logger.warning(f"Timeout waiting for WebSocket connection for user {self.user_id}")
        return False
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register a callback handler for a specific event type."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered handler for {event_type}")
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit an event to all registered handlers."""
        handlers = self.event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")
    
    async def connect(self):
        """Establish WebSocket connection."""
        try:
            logger.info(f"Connecting to WebSocket: {self.ws_url.split('?')[0]}...")
            
            async with websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10) as websocket:
                self.websocket = websocket
                self.is_connected = True
                self.reconnect_attempts = 0
                logger.info(f"WebSocket connected for user {self.user_id}")
                
                # Receive messages from the server
                await self._listen()
        
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            self.is_connected = False
            await self._handle_reconnect()
    
    async def _listen(self):
        """Listen for incoming messages from the server."""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received: {message}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        
        except asyncio.CancelledError:
            logger.info("WebSocket listener cancelled")
            raise
        except Exception as e:
            logger.error(f"WebSocket listener error: {e}")
            self.is_connected = False
            await self._handle_reconnect()
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Process incoming WebSocket message."""
        message_type = data.get("type")
        payload = data.get("payload", {})
        timestamp = data.get("timestamp", datetime.utcnow().isoformat())
        
        logger.debug(f"Received WebSocket message: {message_type}")
        
        # Handle different event types
        if message_type == "CONNECTION_ESTABLISHED":
            logger.info(f"WebSocket connection established: {payload.get('message')}")
            await self._emit_event("CONNECTED", {"user_id": self.user_id, "company_id": self.company_id})
        
        elif message_type == "TASK_HISTORY_UPDATED":
            task_id = payload.get("task_id")
            history_entry = payload.get("history_entry", {})
            
            # Cache the history entry
            if task_id not in self.cached_task_histories:
                self.cached_task_histories[task_id] = []
            self.cached_task_histories[task_id].insert(0, history_entry)  # Most recent first
            
            # Keep only last 50 entries per task
            self.cached_task_histories[task_id] = self.cached_task_histories[task_id][:50]
            
            logger.info(f"Task history updated for task {task_id}")
            await self._emit_event("TASK_HISTORY_UPDATED", {
                "task_id": task_id,
                "history_entry": history_entry,
                "timestamp": timestamp
            })
        
        elif message_type == "COMMENT_ADDED":
            task_id = payload.get("task_id")
            comment = {
                "id": payload.get("id"),
                "content": payload.get("content"),
                "user_name": payload.get("user_name"),
                "user_id": payload.get("user_id"),
                "created_at": payload.get("created_at", timestamp)
            }
            
            # Cache the comment
            if task_id not in self.cached_task_comments:
                self.cached_task_comments[task_id] = []
            self.cached_task_comments[task_id].append(comment)
            
            # Keep only last 50 comments per task
            self.cached_task_comments[task_id] = self.cached_task_comments[task_id][-50:]
            
            logger.info(f"New comment added to task {task_id}")
            await self._emit_event("COMMENT_ADDED", {
                "task_id": task_id,
                "comment": comment,
                "timestamp": timestamp
            })
        
        elif message_type == "COMMENT_DELETED":
            task_id = payload.get("task_id")
            comment_id = payload.get("comment_id")
            
            # Remove from cache
            if task_id in self.cached_task_comments:
                self.cached_task_comments[task_id] = [
                    c for c in self.cached_task_comments[task_id] if c.get("id") != comment_id
                ]
            
            logger.info(f"Comment deleted from task {task_id}")
            await self._emit_event("COMMENT_DELETED", {
                "task_id": task_id,
                "comment_id": comment_id,
                "timestamp": timestamp
            })
        
        elif message_type == "TASK_UPDATED":
            task_id = payload.get("id")
            logger.info(f"Task updated: {task_id}")
            await self._emit_event("TASK_UPDATED", {
                "task": payload,
                "timestamp": timestamp
            })
        
        elif message_type == "TASK_CREATED":
            task_id = payload.get("id")
            logger.info(f"New task created: {task_id}")
            await self._emit_event("TASK_CREATED", {
                "task": payload,
                "timestamp": timestamp
            })
        
        elif message_type == "TASK_DELETED":
            task_id = payload.get("task_id")
            logger.info(f"Task deleted: {task_id}")
            
            # Clear cache for deleted task
            self.cached_task_histories.pop(task_id, None)
            self.cached_task_comments.pop(task_id, None)
            self.cached_task_collaborators.pop(task_id, None)
            
            await self._emit_event("TASK_DELETED", {
                "task_id": task_id,
                "timestamp": timestamp
            })
        
        elif message_type == "TASK_ASSIGNED":
            task_id = payload.get("id")
            logger.info(f"Task assigned: {task_id}")
            await self._emit_event("TASK_ASSIGNED", {
                "task": payload,
                "timestamp": timestamp
            })

        elif message_type == "USER_UPDATED":
            # A user in the company has been updated (name/avatar/etc.)
            user_id = payload.get("user_id") or payload.get("id")
            logger.info(f"User updated: {user_id}")
            await self._emit_event("USER_UPDATED", {
                "user_id": user_id,
                "payload": payload,
                "timestamp": timestamp
            })

        elif message_type == "CHATBOT_DB_CHANGE":
            # Generic chatbot-sourced DB change notification
            logger.info(f"Chatbot DB change: {payload.get('change_type')}")
            await self._emit_event("CHATBOT_DB_CHANGE", {
                "change_type": payload.get("change_type"),
                "details": payload.get("details", {}),
                "timestamp": timestamp
            })
        
        elif message_type == "PONG":
            logger.debug("Received PONG from server")
        
        else:
            logger.debug(f"Unhandled message type: {message_type}")
    
    async def send_ping(self):
        """Send a ping message to keep the connection alive."""
        if self.websocket and self.is_connected:
            try:
                await self.websocket.send(json.dumps({"type": "PING"}))
                logger.debug("Sent PING to server")
            except Exception as e:
                logger.error(f"Error sending PING: {e}")
                self.is_connected = False
    
    async def _handle_reconnect(self):
        """Handle reconnection logic."""
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))  # Exponential backoff
            logger.warning(f"Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts}) in {delay} seconds...")
            await asyncio.sleep(delay)
            await self.connect()
        else:
            logger.error(f"Failed to reconnect after {self.max_reconnect_attempts} attempts")
            self.is_connected = False
    
    def get_task_history(self, task_id: str) -> list:
        """Get cached task history."""
        return self.cached_task_histories.get(task_id, [])
    
    def get_task_comments(self, task_id: str) -> list:
        """Get cached task comments."""
        return self.cached_task_comments.get(task_id, [])
    
    def get_task_collaborators(self, task_id: str) -> list:
        """Get cached task collaborators."""
        return self.cached_task_collaborators.get(task_id, [])
    
    async def start(self):
        """Start the WebSocket connection (usually called in background)."""
        logger.info(f"Starting WebSocket connection for user {self.user_id}")
        while True:
            try:
                logger.debug(f"Attempting to connect to {self.ws_url.split('?')[0]}...")
                await self.connect()
                logger.warning(f"WebSocket connection ended for user {self.user_id}, will retry...")
            except Exception as e:
                logger.error(f"Unexpected error in WebSocket client for user {self.user_id}: {e}", exc_info=True)
            
            # Wait before retry
            if self.reconnect_attempts < self.max_reconnect_attempts:
                delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))
                logger.warning(f"Retrying connection in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"Max reconnection attempts ({self.max_reconnect_attempts}) reached for user {self.user_id}")
                await asyncio.sleep(10)  # Long delay before giving up


# Global WebSocket handlers for different users
_ws_handlers: Dict[str, WebSocketUpdateHandler] = {}


async def get_or_create_ws_handler(
    jwt_token: str,
    user_id: str,
    company_id: str,
    api_url: str = "https://nexus-backend-g0gm.onrender.com"
) -> WebSocketUpdateHandler:
    """Get or create a WebSocket handler for a user."""
    if user_id not in _ws_handlers:
        handler = WebSocketUpdateHandler(jwt_token, user_id, company_id, api_url)
        _ws_handlers[user_id] = handler
        # Start connection in background
        asyncio.create_task(handler.start())
    
    return _ws_handlers[user_id]


def get_ws_handler(user_id: str) -> Optional[WebSocketUpdateHandler]:
    """Get an existing WebSocket handler for a user."""
    return _ws_handlers.get(user_id)


def close_ws_handler(user_id: str):
    """Close a WebSocket handler."""
    if user_id in _ws_handlers:
        handler = _ws_handlers.pop(user_id)
        if handler.websocket:
            asyncio.create_task(handler.websocket.close())
        logger.info(f"Closed WebSocket handler for user {user_id}")
