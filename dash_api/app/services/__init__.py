"""Services package initialization."""
from .auth import AuthService, verify_password, get_password_hash, create_token_pair
from .email import EmailService, send_invitation_email, send_password_reset_email
from .websocket import (
    manager, ConnectionManager, WebSocketEventType,
    notify_task_created, notify_task_updated, notify_task_assigned, notify_task_deleted,
    notify_task_history_updated, notify_task_collaborators_updated,
    notify_project_created, notify_project_updated, notify_project_deleted,
    notify_comment_added, notify_user_invited, notify_invitation_response, notify_user_joined
)

__all__ = [
    "AuthService",
    "verify_password",
    "get_password_hash",
    "create_token_pair",
    "EmailService",
    "send_invitation_email",
    "send_password_reset_email",
    "manager",
    "ConnectionManager",
    "WebSocketEventType",
    "notify_task_created",
    "notify_task_updated",
    "notify_task_assigned",
    "notify_task_deleted",
    "notify_task_history_updated",
    "notify_task_collaborators_updated",
    "notify_project_created",
    "notify_project_updated",
    "notify_project_deleted",
    "notify_comment_added",
    "notify_user_invited",
    "notify_invitation_response",
    "notify_user_joined"
]
