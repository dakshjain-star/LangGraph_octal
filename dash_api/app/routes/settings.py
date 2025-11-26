"""User settings routes."""
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from typing import Optional

from app.schemas.auth import ChangePasswordRequest, MessageResponse
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.auth import hash_password, verify_password
from fastapi import HTTPException

router = APIRouter(prefix="/settings", tags=["Settings"])


class UserSettings(BaseModel):
    """User settings schema."""
    email_notifications: bool = True
    push_notifications: bool = True
    product_updates: bool = True
    two_factor_enabled: bool = False
    public_profile: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "email_notifications": True,
                "push_notifications": True,
                "product_updates": True,
                "two_factor_enabled": False,
                "public_profile": False
            }
        }


class UserSettingsUpdate(BaseModel):
    """User settings update schema."""
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    product_updates: Optional[bool] = None
    two_factor_enabled: Optional[bool] = None
    public_profile: Optional[bool] = None


@router.get(
    "/",
    response_model=UserSettings,
    status_code=status.HTTP_200_OK,
    summary="Get user settings",
    description="Get current user's settings and preferences"
)
async def get_settings(
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's settings including:
    - Email notifications preference
    - Push notifications preference
    - Product updates preference
    - Two-factor authentication status
    - Public profile visibility
    
    Requires authentication.
    """
    return UserSettings(
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile
    )


@router.put(
    "/",
    response_model=UserSettings,
    status_code=status.HTTP_200_OK,
    summary="Update user settings",
    description="Update current user's settings and preferences"
)
async def update_settings(
    settings_data: UserSettingsUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update user settings:
    - **email_notifications**: Enable/disable email notifications
    - **push_notifications**: Enable/disable push notifications
    - **product_updates**: Enable/disable product update emails
    - **two_factor_enabled**: Enable/disable two-factor authentication
    - **public_profile**: Make profile public or private
    
    All fields are optional. Only provided fields will be updated.
    """
    # Update fields if provided
    update_data = {}
    if settings_data.email_notifications is not None:
        update_data["email_notifications"] = settings_data.email_notifications
    if settings_data.push_notifications is not None:
        update_data["push_notifications"] = settings_data.push_notifications
    if settings_data.product_updates is not None:
        update_data["product_updates"] = settings_data.product_updates
    if settings_data.two_factor_enabled is not None:
        update_data["two_factor_enabled"] = settings_data.two_factor_enabled
    if settings_data.public_profile is not None:
        update_data["public_profile"] = settings_data.public_profile
    
    # Update user
    if update_data:
        await current_user.update({"$set": update_data})
        # Reload user to get updated values
        current_user = await User.get(current_user.id)
    
    return UserSettings(
        email_notifications=current_user.email_notifications,
        push_notifications=current_user.push_notifications,
        product_updates=current_user.product_updates,
        two_factor_enabled=current_user.two_factor_enabled,
        public_profile=current_user.public_profile
    )


@router.post(
    "/password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change current user's password"
)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Change user password:
    - **current_password**: Current password for verification
    - **new_password**: New password (minimum 8 characters)
    
    Requires authentication. Current password must be correct.
    """
    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Hash new password
    new_password_hash = hash_password(password_data.new_password)
    
    # Update password
    await current_user.update({"$set": {"password_hash": new_password_hash}})
    
    return MessageResponse(message="Password changed successfully")
