"""Route exports for the FastAPI application."""
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.projects import router as projects_router
from app.routes.tasks import router as tasks_router
from app.routes.comments import router as comments_router
from app.routes.dashboard import router as dashboard_router
from app.routes.settings import router as settings_router
from app.routes.invitations import router as invitations_router
from app.routes.websocket import router as websocket_router

__all__ = [
    "auth_router",
    "users_router",
    "projects_router",
    "tasks_router",
    "comments_router",
    "dashboard_router",
    "settings_router",
    "invitations_router",
    "websocket_router"
]
