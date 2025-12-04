"""Profile management routes for user self-service profile updates."""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status, Form, Body
from typing import Optional
import os
import uuid
import aiofiles
from datetime import datetime
import logging

from app.schemas.user import UserResponse, UserUpdate
from app.models.user import User
from app.middleware.auth import get_current_user
from app.config.settings import settings
from app.services.websocket import notify_user_profile_updated

logger = logging.getLogger(__name__)

router = APIRouter()

# Avatar upload directory
AVATAR_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "avatars")
os.makedirs(AVATAR_UPLOAD_DIR, exist_ok=True)

# Allowed image extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".jfif"}


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user profile",
    description="Get the current logged-in user's profile"
)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get the current user's profile."""
    return UserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=", ".join(current_user.company_names) if current_user.company_names else "Individual",
        company_names=current_user.company_names,
        company_ids=current_user.company_ids,
        current_company_id=current_user.current_company_id,
        current_company_name=current_user.current_company_name,
        avatar_url=current_user.avatar_url,
        status=current_user.status,
        role=current_user.role,
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )


@router.put(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update current user profile",
    description="Update the current logged-in user's profile information"
)
async def update_my_profile(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update the current user's profile (name, email, avatar_url, etc.)."""
    update_data = user_data.model_dump(exclude_unset=True)
    
    # Check if email is being changed and if it's already taken
    if "email" in update_data and update_data["email"] != current_user.email:
        existing_user = await User.find_one(User.email == update_data["email"])
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )
    
    # Update fields
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    current_user.updated_at = datetime.utcnow()
    await current_user.save()
    
    user_response = UserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=", ".join(current_user.company_names) if current_user.company_names else "Individual",
        company_names=current_user.company_names,
        company_ids=current_user.company_ids,
        current_company_id=current_user.current_company_id,
        current_company_name=current_user.current_company_name,
        avatar_url=current_user.avatar_url,
        status=current_user.status,
        role=current_user.role,
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )
    
    # Notify via WebSocket
    company_id = current_user.get_effective_company_id()
    if company_id:
        await notify_user_profile_updated(user_response.model_dump(), company_id)
    
    return user_response


@router.post(
    "/me/avatar",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload avatar image",
    description="Upload an avatar image file (jpg, jpeg, png, gif, webp)"
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload an avatar image file."""
    # Validate file extension
    if not file.filename or not allowed_file(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Validate file size (max 5MB)
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {settings.max_upload_size_mb}MB"
        )
    
    # Generate unique filename
    ext = os.path.splitext(file.filename)[1].lower()
    unique_filename = f"{current_user.id}_{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(AVATAR_UPLOAD_DIR, unique_filename)
    
    # Delete old avatar file if it exists and is a local file
    if current_user.avatar_url:
        old_filename = current_user.avatar_url.split("/")[-1]
        old_file_path = os.path.join(AVATAR_UPLOAD_DIR, old_filename)
        if os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
            except Exception:
                pass  # Ignore deletion errors
    
    # Save new file
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    # Update user's avatar_url to the new file path
    # The URL will be served by the static file endpoint
    avatar_url = f"https://nexus-backend-g0gm.onrender.com/uploads/avatars/{unique_filename}"
    current_user.avatar_url = avatar_url
    current_user.updated_at = datetime.utcnow()
    await current_user.save()
    
    user_response = UserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=", ".join(current_user.company_names) if current_user.company_names else "Individual",
        company_names=current_user.company_names,
        company_ids=current_user.company_ids,
        current_company_id=current_user.current_company_id,
        current_company_name=current_user.current_company_name,
        avatar_url=current_user.avatar_url,
        status=current_user.status,
        role=current_user.role,
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )
    
    # Notify via WebSocket
    company_id = current_user.get_effective_company_id()
    if company_id:
        await notify_user_profile_updated(user_response.model_dump(), company_id)
    
    return user_response


@router.delete(
    "/me/avatar",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete avatar",
    description="Remove the current user's avatar"
)
async def delete_avatar(current_user: User = Depends(get_current_user)):
    """Delete the current user's avatar."""
    # Delete avatar file if it exists and is a local file
    if current_user.avatar_url:
        old_filename = current_user.avatar_url.split("/")[-1]
        old_file_path = os.path.join(AVATAR_UPLOAD_DIR, old_filename)
        if os.path.exists(old_file_path):
            try:
                os.remove(old_file_path)
            except Exception:
                pass  # Ignore deletion errors
    
    # Clear avatar_url
    current_user.avatar_url = None
    current_user.updated_at = datetime.utcnow()
    await current_user.save()
    
    user_response = UserResponse(
        id=str(current_user.id),
        name=current_user.name,
        email=current_user.email,
        company_name=", ".join(current_user.company_names) if current_user.company_names else "Individual",
        company_names=current_user.company_names,
        company_ids=current_user.company_ids,
        current_company_id=current_user.current_company_id,
        current_company_name=current_user.current_company_name,
        avatar_url=current_user.avatar_url,
        status=current_user.status,
        role=current_user.role,
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )
    
    # Notify via WebSocket
    company_id = current_user.get_effective_company_id()
    if company_id:
        await notify_user_profile_updated(user_response.model_dump(), company_id)
    
    return user_response


@router.post(
    "/webhook/notify-update",
    status_code=status.HTTP_200_OK,
    summary="Webhook for chatbot profile updates",
    description="Internal webhook endpoint for chatbot to notify about profile changes"
)
async def webhook_notify_profile_update(
    user_data: dict = Body(...)
):
    """
    Internal webhook endpoint to receive profile update notifications from chatbot.
    This is used because the chatbot runs in a separate process without direct access
    to the WebSocket manager.
    """
    try:
        logger.info(f"[WEBHOOK] Received profile update notification for user: {user_data.get('id')}")
        company_id = user_data.get('company_id')
        
        if not company_id:
            logger.warning("[WEBHOOK] No company_id provided in webhook payload")
            return {"status": "error", "message": "No company_id provided"}
        
        # Clean the user_data before broadcasting
        broadcast_data = {
            k: v for k, v in user_data.items() 
            if k != 'company_id'  # Don't broadcast company_id as part of user data
        }
        
        # Send WebSocket notification to all users in the company
        await notify_user_profile_updated(broadcast_data, company_id)
        
        logger.info(f"[WEBHOOK] Successfully notified company {company_id} about user profile update")
        return {"status": "success", "message": "Profile update notification sent"}
        
    except Exception as e:
        logger.error(f"[WEBHOOK] Error processing profile update notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing webhook: {str(e)}"
        )

