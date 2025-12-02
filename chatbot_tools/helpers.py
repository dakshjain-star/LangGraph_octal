"""
Core helpers for LangGraph chatbot tools.
Contains run_async, event loop management, and WebSocket notifications.
"""
import asyncio
import logging
import os
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Store reference to main event loop
_main_loop: Optional[asyncio.AbstractEventLoop] = None

# dash_api base URL (where WebSocket connections are managed)
DASH_API_BASE_URL = os.environ.get("DASH_API_URL", "http://localhost:8000")


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop reference (call from FastAPI startup)."""
    global _main_loop
    _main_loop = loop
    logger.info(f"Main event loop set: {loop}")


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Get the main event loop reference."""
    return _main_loop


# --- WebSocket Notification Helper ---
async def _notify_chatbot_db_change(company_id: str, change_type: str, details: dict = None):
    """Send WebSocket notification when chatbot makes a DB change.
    
    This makes an HTTP request to the dash_api server (port 8000) to trigger
    the WebSocket broadcast. This is necessary because the chatbot runs on
    a separate process (port 8081) and doesn't share the WebSocket connection
    manager with dash_api.
    """
    try:
        logger.info(f"[CHATBOT TOOLS] Attempting to notify via HTTP: {change_type} for company {company_id}")
        logger.info(f"[CHATBOT TOOLS] Details: {details}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DASH_API_BASE_URL}/api/v1/ws/chatbot-notify",
                json={
                    "company_id": company_id,
                    "change_type": change_type,
                    "details": details or {}
                },
                headers={
                    "X-Internal-Secret": "chatbot-internal-secret",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[CHATBOT TOOLS] ✓ Successfully sent notification: {change_type}")
                logger.info(f"[CHATBOT TOOLS] ✓ Users notified: {result.get('users_notified', 0)}")
            else:
                logger.error(f"[CHATBOT TOOLS] ✗ HTTP notification failed: {response.status_code} - {response.text}")
                
    except httpx.ConnectError as e:
        logger.error(f"[CHATBOT TOOLS] ✗ Cannot connect to dash_api at {DASH_API_BASE_URL}: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[CHATBOT TOOLS] ✗ Failed to send notification: {e}")
        logger.error(f"[CHATBOT TOOLS] Traceback: {traceback.format_exc()}")


async def _notify_invitation_to_user(invitee_user_id: str, invitation_data: dict):
    """Send WebSocket notification directly to a specific user when they receive an invitation.
    
    This makes an HTTP request to the dash_api server (port 8000) to trigger
    a USER_INVITED WebSocket event to the specific user.
    """
    try:
        logger.info(f"[CHATBOT TOOLS] Sending invitation notification to user: {invitee_user_id}")
        logger.info(f"[CHATBOT TOOLS] Invitation data: {invitation_data}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DASH_API_BASE_URL}/api/v1/ws/invitation-notify",
                json={
                    "invitee_user_id": invitee_user_id,
                    "invitation_data": invitation_data
                },
                headers={
                    "X-Internal-Secret": "chatbot-internal-secret",
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"[CHATBOT TOOLS] ✓ Invitation notification sent to user: {invitee_user_id}")
                logger.info(f"[CHATBOT TOOLS] ✓ User online: {result.get('user_online', False)}")
            else:
                logger.error(f"[CHATBOT TOOLS] ✗ Invitation notification failed: {response.status_code} - {response.text}")
                
    except httpx.ConnectError as e:
        logger.error(f"[CHATBOT TOOLS] ✗ Cannot connect to dash_api at {DASH_API_BASE_URL}: {e}")
    except Exception as e:
        import traceback
        logger.error(f"[CHATBOT TOOLS] ✗ Failed to send invitation notification: {e}")
        logger.error(f"[CHATBOT TOOLS] Traceback: {traceback.format_exc()}")


# --- Async Helper ---
def run_async(coro):
    """Run async code in sync context for LangGraph tools.
    
    This handles running async operations from ThreadPoolExecutor threads
    by scheduling them on the main event loop.
    """
    global _main_loop
    
    # If we have a reference to the main loop and it's running, schedule on it
    if _main_loop is not None and _main_loop.is_running():
        try:
            # Use thread-safe method to run coroutine on the main loop
            future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
            # Use a shorter timeout to catch issues faster
            return future.result(timeout=30)
        except TimeoutError:
            logger.error("Async operation timed out after 30 seconds")
            # Cancel the future if possible
            future.cancel()
            return "Error: Operation timed out. Please try again."
        except Exception as e:
            # Log full traceback for debugging
            import traceback
            logger.error(f"Error in run_async (main loop): {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error: {str(e)}"
    
    # Fallback: try to create a new event loop for this thread
    try:
        loop = asyncio.get_running_loop()
        # We're in a thread with a running loop - schedule on it
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    except RuntimeError:
        # No running loop in this thread - create a new one
        try:
            # Create a new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            import traceback
            logger.error(f"Error creating new event loop: {type(e).__name__}: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error: {str(e)}"
