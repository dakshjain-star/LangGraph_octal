"""User controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional
import re
from datetime import datetime

from app.models.user import User, UserStatus, UserRole
from app.schemas.user import (
    UserUpdate, UserRoleUpdate, UserStatusUpdate, 
    UserInviteRequest, UserResponse
)
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
        limit: int = 50
    ) -> Dict:
        """Get all users with optional filters."""
        query = {}
        
        # Apply filters
        if status:
            query["status"] = status
        
        if role:
            query["role"] = role
        
        if search:
            # Case-insensitive regex search on name and email
            search_regex = re.compile(re.escape(search), re.IGNORECASE)
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
                company_name=user.company_name,
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
        
        return {
            "users": user_responses,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> UserResponse:
        """Get a single user by ID."""
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=user.company_name,
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
            company_name=user.company_name,
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
            company_name=user.company_name,
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
            company_name=user.company_name,
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
        """Delete a user (admin only)."""
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete users"
            )
        
        # Check if user exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent self-deletion
        if str(user.id) == str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Delete user
        await user.delete()
        
        return {"message": "User deleted successfully"}
    
    @staticmethod
    async def invite_user(data: UserInviteRequest, current_user: User) -> UserResponse:
        """Invite a new user (admin only)."""
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can invite users"
            )
        
        # Check if user already exists
        existing_user = await User.find_one(User.email == data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Generate temporary password
        temp_password = secrets.token_urlsafe(16)
        
        # Create invited user
        user = User(
            name=data.name,
            email=data.email,
            password_hash=get_password_hash(temp_password),
            company_name=current_user.company_name,
            status=UserStatus.INVITED,
            role=data.role
        )
        
        await user.insert()
        
        # Send invitation email with temporary password
        # In production, this would send a proper invitation link
        await send_password_reset_email(
            to_email=user.email,
            to_name=user.name,
            reset_link=f"http://localhost:3000/login?email={user.email}"
        )
        
        return UserResponse(
            id=str(user.id),
            name=user.name,
            email=user.email,
            company_name=user.company_name,
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
    async def search_users(query: str) -> List[UserResponse]:
        """Search users by name or email."""
        if not query or len(query.strip()) == 0:
            return []
        
        # Case-insensitive regex search
        search_regex = re.compile(re.escape(query), re.IGNORECASE)
        
        users = await User.find(
            {
                "$or": [
                    {"name": search_regex},
                    {"email": search_regex}
                ],
                "status": UserStatus.ACTIVE
            }
        ).limit(20).to_list()
        
        return [
            UserResponse(
                id=str(user.id),
                name=user.name,
                email=user.email,
                company_name=user.company_name,
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
