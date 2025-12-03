"""
Profile management tools for LangGraph chatbot.
Allows users to update their profile information via natural language.
"""
import logging
from typing import Optional
from langchain_core.tools import tool
from datetime import datetime
import re

from chatbot_tools.helpers import run_async, _notify_chatbot_db_change

logger = logging.getLogger(__name__)


# --- Async Implementations ---

async def _update_profile_async(
    db,
    user_id: str,
    company_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    avatar_url: Optional[str] = None
) -> str:
    """Update user profile information."""
    from bson import ObjectId
    
    try:
        users_collection = db.users
        
        # Build update document
        update_doc = {"$set": {"updated_at": datetime.utcnow()}}
        updates_made = []
        
        if name and name.strip():
            update_doc["$set"]["name"] = name.strip()
            updates_made.append(f"name to '{name.strip()}'")
        
        if email and email.strip():
            # Validate email format
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, email.strip()):
                return f"Invalid email format: {email}"
            
            # Check if email is already in use
            existing = await users_collection.find_one({"email": email.strip(), "_id": {"$ne": ObjectId(user_id)}})
            if existing:
                return f"Email '{email}' is already in use by another user."
            
            update_doc["$set"]["email"] = email.strip()
            updates_made.append(f"email to '{email.strip()}'")
        
        if avatar_url is not None:  # Allow empty string to remove avatar
            if avatar_url.strip():
                # Basic URL validation
                if not avatar_url.startswith(('http://', 'https://')):
                    return f"Avatar URL must start with http:// or https://"
                update_doc["$set"]["avatar_url"] = avatar_url.strip()
                updates_made.append("avatar")
            else:
                # Remove avatar
                update_doc["$set"]["avatar_url"] = None
                updates_made.append("removed avatar")
        
        if not updates_made:
            return "No profile changes specified. You can update: name, email, or avatar_url."
        
        # Perform update
        result = await users_collection.update_one(
            {"_id": ObjectId(user_id)},
            update_doc
        )
        
        if result.modified_count == 0:
            return "No changes were made. The profile may already have these values."
        
        # Fetch updated user data for WebSocket notification
        updated_user = await users_collection.find_one({"_id": ObjectId(user_id)})
        
        # Notify via HTTP request to main API's webhook endpoint for WebSocket broadcast
        if updated_user:
            try:
                import aiohttp
                from chatbot_tools.helpers import DASH_API_BASE_URL
                
                webhook_url = f"{DASH_API_BASE_URL}/profile/webhook/notify-update"
                user_data = {
                    "id": str(updated_user["_id"]),
                    "name": updated_user.get("name"),
                    "email": updated_user.get("email"),
                    "avatar_url": updated_user.get("avatar_url"),
                    "role": updated_user.get("role"),
                    "status": updated_user.get("status"),
                    "company_id": company_id,
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=user_data) as resp:
                        if resp.status != 200:
                            logger.warning(f"WebSocket notification HTTP request failed: {resp.status}")
            except Exception as ws_err:
                logger.warning(f"WebSocket notification via HTTP failed: {ws_err}")
        
        # Also send chatbot DB change notification for general refresh
        await _notify_chatbot_db_change(
            company_id=company_id,
            change_type="user_profile_updated",
            details={
                "user_id": user_id,
                "updates": updates_made
            }
        )
        
        return f"Profile updated successfully! Changed: {', '.join(updates_made)}."
        
    except Exception as e:
        logger.error(f"Error updating profile: {e}")
        return f"Failed to update profile: {str(e)}"


async def _get_my_profile_async(db, user_id: str) -> str:
    """Get current user's profile information."""
    from bson import ObjectId
    
    try:
        users_collection = db.users
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        
        if not user:
            return "Could not find your profile."
        
        profile_info = f"""
**Your Profile:**
- **Name:** {user.get('name', 'Not set')}
- **Email:** {user.get('email', 'Not set')}
- **Avatar:** {'Set ✓' if user.get('avatar_url') else 'Not set'}
- **Company:** {', '.join(user.get('company_names', [])) or user.get('company_name', 'Individual')}
- **Role:** {user.get('role', 'Member')}
- **Status:** {user.get('status', 'Active')}

You can update your name, email, or avatar using commands like:
- "Update my name to John Smith"
- "Change my email to john@example.com"
- "Set my avatar to https://example.com/photo.jpg"
- "Remove my avatar"
"""
        return profile_info.strip()
        
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        return f"Failed to get profile: {str(e)}"


# --- Tool Definitions ---

def create_profile_tools(db_getter, user_id_getter, company_id_getter):
    """Create profile management tools with injected dependencies.
    
    Args:
        db_getter: Callable that returns the database instance
        user_id_getter: Callable that returns the current user ID
        company_id_getter: Callable that returns the current company ID
    """
    
    @tool
    def update_my_profile(
        name: Optional[str] = None,
        email: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> str:
        """Update your profile information.
        
        Use this tool when the user wants to:
        - Change their name
        - Update their email address
        - Set or change their avatar/profile picture URL
        - Remove their avatar
        
        Args:
            name: New name for the user (optional)
            email: New email address (optional, must be valid format)
            avatar_url: URL for profile picture (optional, must be http/https URL, empty string to remove)
            
        Returns:
            Success message with what was updated, or error message.
        """
        db = db_getter()
        user_id = user_id_getter()
        company_id = company_id_getter()
        
        if db is None or user_id is None:
            return "Unable to update profile: user context not available."
        
        return run_async(_update_profile_async(
            db=db,
            user_id=user_id,
            company_id=company_id or "",
            name=name,
            email=email,
            avatar_url=avatar_url
        ))
    
    @tool
    def get_my_profile() -> str:
        """Get your current profile information.
        
        Use this tool when the user wants to:
        - View their profile
        - See their current information
        - Check their name, email, or avatar
        
        Returns:
            Formatted profile information including name, email, company, role, etc.
        """
        db = db_getter()
        user_id = user_id_getter()
        
        if db is None or user_id is None:
            return "Unable to get profile: user context not available."
        
        return run_async(_get_my_profile_async(db=db, user_id=user_id))
    
    @tool
    def set_my_avatar(avatar_url: str) -> str:
        """Set or update your profile avatar/picture.
        
        Use this tool when the user wants to:
        - Set a profile picture
        - Change their avatar
        - Update their photo
        
        Args:
            avatar_url: URL of the image to use as avatar (must be http or https URL)
            
        Returns:
            Success or error message.
        """
        db = db_getter()
        user_id = user_id_getter()
        company_id = company_id_getter()
        
        if db is None or user_id is None:
            return "Unable to update avatar: user context not available."
        
        return run_async(_update_profile_async(
            db=db,
            user_id=user_id,
            company_id=company_id or "",
            avatar_url=avatar_url
        ))
    
    @tool
    def remove_my_avatar() -> str:
        """Remove your profile avatar/picture.
        
        Use this tool when the user wants to:
        - Remove their profile picture
        - Delete their avatar
        - Clear their photo
        
        Returns:
            Success or error message.
        """
        db = db_getter()
        user_id = user_id_getter()
        company_id = company_id_getter()
        
        if db is None or user_id is None:
            return "Unable to remove avatar: user context not available."
        
        return run_async(_update_profile_async(
            db=db,
            user_id=user_id,
            company_id=company_id or "",
            avatar_url=""  # Empty string to remove
        ))
    
    @tool
    def change_my_name(new_name: str) -> str:
        """Change your display name.
        
        Use this tool when the user wants to:
        - Change their name
        - Update their display name
        
        Args:
            new_name: The new name to set
            
        Returns:
            Success or error message.
        """
        db = db_getter()
        user_id = user_id_getter()
        company_id = company_id_getter()
        
        if db is None or user_id is None:
            return "Unable to update name: user context not available."
        
        if not new_name or not new_name.strip():
            return "Please provide a valid name."
        
        return run_async(_update_profile_async(
            db=db,
            user_id=user_id,
            company_id=company_id or "",
            name=new_name
        ))
    
    return [
        update_my_profile,
        get_my_profile,
        set_my_avatar,
        remove_my_avatar,
        change_my_name
    ]
