"""User controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional
import re
from datetime import datetime

from app.models.user import User, UserStatus, UserRole
from app.models.invitation import Invitation, InvitationStatus
from app.schemas.user import (
    UserUpdate, UserRoleUpdate, UserStatusUpdate, 
    UserInviteRequest, UserResponse
)
from app.schemas.invitation import InvitationResponse
from app.services.auth import get_password_hash
from app.services.email import send_password_reset_email
import secrets


class UserController:
    """User controller for handling user operations."""
    
    @staticmethod
    async def get_all_users(
        status: Optional[UserStatus] = None,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
        current_user: User = None
    ) -> List[UserResponse]:
        """Get all users with optional filters."""
        query = {}
        
        # Filter by company - users can only see users in their current company
        # Search for users in both new and legacy company fields
        if current_user and current_user.get_effective_company_id():
            effective_company_id = current_user.get_effective_company_id()
            query["$or"] = [
                {"company_ids": effective_company_id},  # New field (array)
                {"company_id": effective_company_id}     # Legacy field (single)
            ]
        
        # Apply filters
        if status:
            query["status"] = status
        
        if role:
            query["role"] = role
        
        if search:
            # Case-insensitive regex search on name and email
            search_regex = re.compile(re.escape(search), re.IGNORECASE)
            # Combine with existing $or if present
            if "$or" in query:
                query = {
                    "$and": [
                        {"$or": query["$or"]},
                        {"$or": [{"name": search_regex}, {"email": search_regex}]}
                    ]
                }
                if status:
                    query["status"] = status
                if role:
                    query["role"] = role
            else:
                query["$or"] = [
                    {"name": search_regex},
                    {"email": search_regex}
                ]
        
        # Get total count
        total = await User.find(query).count()
        
        # Get users with pagination
        users = await User.find(query).skip(skip).limit(limit).to_list()
        
        # Convert to response format
        user_responses = [
            UserResponse(
                id=str(user.id),
                name=user.name,
                email=user.email,
                company_name=", ".join(user.company_names) if user.company_names else "Individual",
                company_names=user.company_names,
                company_ids=user.company_ids,
                current_company_id=user.current_company_id,
                current_company_name=user.current_company_name,
                avatar_url=user.avatar_url,
                status=user.status,
                role=user.role,
                email_notifications=user.email_notifications,
                push_notifications=user.push_notifications,
                product_updates=user.product_updates,
                two_factor_enabled=user.two_factor_enabled,
                public_profile=user.public_profile,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            for user in users
        ]
        
        return user_responses
    
    @staticmethod
    async def get_user_by_id(user_id: str, current_user: User = None) -> UserResponse:
        """Get a single user by ID."""
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check company access - users can only view users who share at least one company
        if current_user and current_user.get_effective_company_id():
            user_company_ids = user.get_effective_company_ids() if hasattr(user, 'get_effective_company_ids') else (user.company_ids or ([user.company_id] if user.company_id else []))
            if current_user.get_effective_company_id() not in user_company_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not authorized to view this user"
                )
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=", ".join(user.company_names) if user.company_names else "Individual",
            company_names=user.company_names,
            company_ids=user.company_ids,
            current_company_id=user.current_company_id,
            current_company_name=user.current_company_name,
            avatar_url=user.avatar_url,
            status=user.status,
            role=user.role,
            email_notifications=user.email_notifications,
            push_notifications=user.push_notifications,
            product_updates=user.product_updates,
            two_factor_enabled=user.two_factor_enabled,
            public_profile=user.public_profile,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    
    @staticmethod
    async def update_user(user_id: str, data: UserUpdate, current_user: User) -> UserResponse:
        """Update user information."""
        # Check if user exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check permissions - users can update themselves, or admin can update anyone
        if str(user.id) != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this user"
            )
        
        # Check if email is being changed and if it's already taken
        if data.email and data.email != user.email:
            existing_user = await User.find_one(User.email == data.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        user.updated_at = datetime.utcnow()
        await user.save()
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=", ".join(user.company_names) if user.company_names else "Individual",
            company_names=user.company_names,
            company_ids=user.company_ids,
            current_company_id=user.current_company_id,
            current_company_name=user.current_company_name,
            avatar_url=user.avatar_url,
            status=user.status,
            role=user.role,
            email_notifications=user.email_notifications,
            push_notifications=user.push_notifications,
            product_updates=user.product_updates,
            two_factor_enabled=user.two_factor_enabled,
            public_profile=user.public_profile,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    
    @staticmethod
    async def update_user_role(user_id: str, data: UserRoleUpdate, current_user: User) -> UserResponse:
        """Update user role (admin only)."""
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user roles"
            )
        
        # Check if user exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-demotion
        if str(user.id) == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own role"
            )
        
        # Update role
        user.role = data.role
        user.updated_at = datetime.utcnow()
        await user.save()
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=", ".join(user.company_names) if user.company_names else "Individual",
            company_names=user.company_names,
            company_ids=user.company_ids,
            current_company_id=user.current_company_id,
            current_company_name=user.current_company_name,
            avatar_url=user.avatar_url,
            status=user.status,
            role=user.role,
            email_notifications=user.email_notifications,
            push_notifications=user.push_notifications,
            product_updates=user.product_updates,
            two_factor_enabled=user.two_factor_enabled,
            public_profile=user.public_profile,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    
    @staticmethod
    async def update_user_status(user_id: str, data: UserStatusUpdate, current_user: User) -> UserResponse:
        """Update user status (admin only)."""
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can change user status"
            )
        
        # Check if user exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deactivation
        if str(user.id) == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change your own status"
            )
        
        # Update status
        user.status = data.status
        user.updated_at = datetime.utcnow()
        await user.save()
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=", ".join(user.company_names) if user.company_names else "Individual",
            company_names=user.company_names,
            company_ids=user.company_ids,
            current_company_id=user.current_company_id,
            current_company_name=user.current_company_name,
            avatar_url=user.avatar_url,
            status=user.status,
            role=user.role,
            email_notifications=user.email_notifications,
            push_notifications=user.push_notifications,
            product_updates=user.product_updates,
            two_factor_enabled=user.two_factor_enabled,
            public_profile=user.public_profile,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    
    @staticmethod
    async def delete_user(user_id: str, current_user: User) -> Dict:
        """Remove a user from the company (admin only).
        
        This does not delete the user from the database.
        Instead, it changes their company_name to 'Individual' and role to 'Member'.
        """
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can remove users from company"
            )
        
        # Check if user exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-removal
        if str(user.id) == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove yourself from the company"
            )
        
        # Check if user belongs to the same company
        user_company_ids = user.get_effective_company_ids() if hasattr(user, 'get_effective_company_ids') else (user.company_ids or ([user.company_id] if user.company_id else []))
        if current_user.get_effective_company_id() not in user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove users from other companies"
            )
        
        # Remove user from the current company (don't remove from all companies)
        effective_company_id = current_user.get_effective_company_id()
        if effective_company_id in (user.company_ids or []):
            user.company_ids.remove(effective_company_id)
        
        # Also update the legacy company_id if it matches
        if user.company_id == effective_company_id:
            user.company_id = None
            user.company_name = None
        
        effective_company_name = current_user.current_company_name or current_user.company_name
        if effective_company_name and effective_company_name in (user.company_names or []):
            user.company_names.remove(effective_company_name)
        
        # Update the current company to another one if available, or set to None
        if user.company_ids:
            user.current_company_id = user.company_ids[0]
            user.current_company_name = user.company_names[0] if user.company_names else None
        else:
            user.current_company_id = None
            user.current_company_name = None
            user.role = UserRole.MEMBER  # Reset role to Member when no companies
        
        user.updated_at = datetime.utcnow()
        await user.save()
        
        return {"message": "User removed from company successfully"}
    
    @staticmethod
    async def invite_user(data: UserInviteRequest, current_user: User) -> InvitationResponse:
        """Invite an existing user to join company (admin only)."""
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can invite users"
            )
        
        # Check if user exists (must be registered first)
        existing_user = await User.find_one(User.email == data.email)
        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User with this email is not registered. They must register first."
            )
        
        # Check if user is already in this company
        existing_user_company_ids = existing_user.get_effective_company_ids() if hasattr(existing_user, 'get_effective_company_ids') else (existing_user.company_ids or ([existing_user.company_id] if existing_user.company_id else []))
        if current_user.get_effective_company_id() in existing_user_company_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of your company"
            )
        
        # Check if invitation already exists and is pending
        existing_invitation = await Invitation.find_one(
            Invitation.invitee_email == data.email,
            Invitation.company_id == current_user.get_effective_company_id(),
            Invitation.status == InvitationStatus.PENDING
        )
        if existing_invitation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An invitation has already been sent to this user"
            )
        
        # Create invitation
        effective_company_name = current_user.current_company_name or current_user.company_name
        invitation = Invitation(
            invitee_email=data.email,
            invitee_user_id=str(existing_user.id),
            company_id=current_user.get_effective_company_id(),
            company_name=effective_company_name,
            inviter_id=str(current_user.id),
            inviter_name=current_user.name,
            role=data.role.value if hasattr(data.role, 'value') else str(data.role),
            status=InvitationStatus.PENDING
        )
        
        await invitation.insert()
        
        # Optionally send email notification
        # await send_invitation_email(...)
        
        return InvitationResponse(
            id=str(invitation.id),
            invitee_email=invitation.invitee_email,
            invitee_user_id=invitation.invitee_user_id,
            company_name=invitation.company_name,
            company_id=invitation.company_id,
            inviter_id=invitation.inviter_id,
            inviter_name=invitation.inviter_name,
            role=invitation.role,
            status=invitation.status,
            created_at=invitation.created_at,
            updated_at=invitation.updated_at,
            expires_at=invitation.expires_at
        )
    
    @staticmethod
    async def search_users(query: str, current_user: User = None) -> List[UserResponse]:
        """Search users by name or email."""
        if not query or len(query.strip()) == 0:
            return []
        
        # Case-insensitive regex search
        search_regex = re.compile(re.escape(query), re.IGNORECASE)
        
        # Build query with company filter
        search_query = {
            "$or": [
                {"name": search_regex},
                {"email": search_regex}
            ],
            "status": UserStatus.ACTIVE
        }
        
        # Filter by company if current_user is provided
        # Search for users in both new and legacy company fields
        if current_user and current_user.get_effective_company_id():
            effective_company_id = current_user.get_effective_company_id()
            search_query["$and"] = [
                {"$or": [
                    {"company_ids": effective_company_id},  # New field (array)
                    {"company_id": effective_company_id}     # Legacy field (single)
                ]}
            ]
        
        users = await User.find(search_query).limit(20).to_list()
        
        return [
            UserResponse(
                id=str(user.id),
                name=user.name,
                email=user.email,
                company_name=", ".join(user.company_names) if user.company_names else "Individual",
                company_names=user.company_names,
                company_ids=user.company_ids,
                current_company_id=user.current_company_id,
                current_company_name=user.current_company_name,
                avatar_url=user.avatar_url,
                status=user.status,
                role=user.role,
                email_notifications=user.email_notifications,
                push_notifications=user.push_notifications,
                product_updates=user.product_updates,
                two_factor_enabled=user.two_factor_enabled,
                public_profile=user.public_profile,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            for user in users
        ]
