"""User management routes."""
from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional

from app.schemas.user import (
    UserResponse,
    UserUpdate,
    UserRoleUpdate,
    UserStatusUpdate,
    UserInviteRequest,
    UserStatus,
    UserRole
)
from app.schemas.invitation import InvitationResponse
from app.schemas.auth import MessageResponse
from app.controllers.user_controller import UserController
from app.middleware.auth import (
    get_current_user,
    require_admin,
    require_member_or_admin
)
from app.models.user import User

router = APIRouter()


@router.get(
    "/",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Get all users",
    description="Retrieve list of all users with optional filters"
)
async def get_users(
    status_filter: Optional[List[UserStatus]] = Query(None, alias="status"),
    role: Optional[List[UserRole]] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user)
):
    """
    Get all users with optional filtering:
    - **status**: Filter by user status (Active, Invited)
    - **role**: Filter by user role (Admin, Member, Viewer)
    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    
    Requires authentication.
    """
    return await UserController.get_all_users(
        status=status_filter,
        role=role,
        skip=skip,
        limit=limit,
        current_user=current_user
    )


@router.get(
    "/search",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Search users",
    description="Search users by name or email"
)
async def search_users(
    query: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user)
):
    """
    Search users by name or email:
    - **query**: Search query string
    
    Returns users matching the search criteria.
    """
    return await UserController.search_users(query, current_user)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get user by ID",
    description="Retrieve a specific user by their ID"
)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific user by ID.
    
    - **user_id**: The ID of the user to retrieve
    
    Requires authentication.
    """
    return await UserController.get_user_by_id(user_id, current_user)


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user",
    description="Update user information"
)
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user)
):
    """
    Update user information:
    - **user_id**: The ID of the user to update
    - **user_data**: Updated user information (all fields optional)
    
    Users can update their own profile. Admins can update any user.
    """
    return await UserController.update_user(user_id, user_data, current_user)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user role",
    description="Update a user's role (admin only)"
)
async def update_user_role(
    user_id: str,
    role_data: UserRoleUpdate,
    current_user: User = Depends(require_admin)
):
    """
    Update a user's role (admin only):
    - **user_id**: The ID of the user to update
    - **role**: New role (Admin, Member, Viewer)
    
    Requires admin privileges.
    """
    return await UserController.update_user_role(user_id, role_data, current_user)


@router.patch(
    "/{user_id}/status",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update user status",
    description="Update a user's status (admin only)"
)
async def update_user_status(
    user_id: str,
    status_data: UserStatusUpdate,
    current_user: User = Depends(require_admin)
):
    """
    Update a user's status (admin only):
    - **user_id**: The ID of the user to update
    - **status**: New status (Active, Invited)
    
    Requires admin privileges.
    """
    return await UserController.update_user_status(user_id, status_data, current_user)


@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete user",
    description="Delete a user (admin only)"
)
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin)
):
    """
    Delete a user (admin only):
    - **user_id**: The ID of the user to delete
    
    Requires admin privileges. Cannot delete yourself.
    """
    return await UserController.delete_user(user_id, current_user)


@router.post(
    "/invite",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invite user",
    description="Invite an existing user to join your company"
)
async def invite_user(
    invite_data: UserInviteRequest,
    current_user: User = Depends(require_admin)
):
    """
    Invite an existing user to join your company:
    - **email**: Email address of the registered user to invite
    - **role**: Role to assign upon acceptance (default: Member)
    
    The user must already be registered. Creates an invitation that the user can accept or decline.
    Requires Admin role.
    """
    return await UserController.invite_user(invite_data, current_user)
