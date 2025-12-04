"""Authentication controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict

from app.models.user import User, UserStatus, UserRole
from app.models.company import Company
from app.schemas.auth import (
    RegisterRequest, LoginRequest, RefreshTokenRequest,
    ForgotPasswordRequest, ResetPasswordRequest
)
from app.services.auth import (
    verify_password, get_password_hash,
    create_token_pair, verify_token, AuthService
)
from app.services.email import send_password_reset_email


class AuthController:
    """Authentication controller for handling auth operations."""
    
    @staticmethod
    async def register(data: RegisterRequest) -> Dict:
        """Register a new user."""
        # Check if user already exists
        existing_user = await User.find_one(User.email == data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Check if this is the first user for this company (they become Admin)
        # Look up by company name first
        existing_company = await Company.find_one(Company.name == data.company_name)
        
        company_id = None
        user_role = UserRole.MEMBER
        company_ids = []
        company_names = []
        
        if not existing_company:
            # This is a new company - user becomes Admin
            user_role = UserRole.ADMIN
            # We'll create the company after creating the user (need user id)
        else:
            # Company exists, user joins as Member
            company_id = str(existing_company.id)
            company_ids = [company_id]
            company_names = [data.company_name]
        
        # Create new user
        user = User(
            name=data.name,
            email=data.email,
            password_hash=get_password_hash(data.password),
            company_ids=company_ids,
            company_names=company_names,
            current_company_id=company_id,
            current_company_name=data.company_name if company_id else None,
            status=UserStatus.ACTIVE,
            role=user_role
        )
        
        await user.insert()
        
        # If this is a new company, create it now with the user as owner
        if not existing_company:
            company = Company(
                name=data.company_name,
                owner_id=str(user.id),
                owner_name=user.name,
                owner_email=user.email
            )
            await company.insert()
            
            # Update user with company_id
            user.company_ids = [str(company.id)]
            user.company_names = [data.company_name]
            user.current_company_id = str(company.id)
            user.current_company_name = data.company_name
            await user.save()
        
        # Create tokens
        tokens = create_token_pair(str(user.id), user.email)
        
        return {
            **tokens,
            "user": user.dict_without_password()
        }
    
    @staticmethod
    async def login(data: LoginRequest) -> Dict:
        """Login user and return tokens."""
        # Find user by email
        user = await User.find_one(User.email == data.email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Verify password
        if not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )
        
        # Check if user is active
        if user.status != UserStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active"
            )
        
        # Create tokens
        tokens = create_token_pair(str(user.id), user.email)
        
        return {
            **tokens,
            "user": user.dict_without_password()
        }
    
    @staticmethod
    async def refresh_token(data: RefreshTokenRequest) -> Dict:
        """Refresh access token using refresh token."""
        # Verify refresh token
        payload = verify_token(data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        user_id = payload.get("sub")
        email = payload.get("email")
        
        # Verify user still exists
        user = await User.get(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        # Create new token pair
        tokens = create_token_pair(user_id, email)
        
        return tokens
    
    @staticmethod
    async def get_current_user_info(user: User) -> Dict:
        """Get current user information."""
        return user.dict_without_password()
    
    @staticmethod
    async def forgot_password(data: ForgotPasswordRequest) -> Dict:
        """Send password reset email."""
        # Find user by email
        user = await User.find_one(User.email == data.email)
        if not user:
            # Don't reveal if email exists or not (security best practice)
            return {"message": "If the email exists, a password reset link has been sent"}
        
        # Create password reset token
        reset_token = AuthService.create_password_reset_token(user.email)
        
        # In production, this would be your frontend URL
        reset_link = f"https://nexus-esw7.onrender.com/reset-password?token={reset_token}"
        
        # Send email
        await send_password_reset_email(
            to_email=user.email,
            to_name=user.name,
            reset_link=reset_link
        )
        
        return {"message": "If the email exists, a password reset link has been sent"}
    
    @staticmethod
    async def reset_password(data: ResetPasswordRequest) -> Dict:
        """Reset password using token."""
        # Verify token
        payload = verify_token(data.token, token_type="password_reset")
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        email = payload.get("sub")
        
        # Find user
        user = await User.find_one(User.email == email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update password
        user.password_hash = get_password_hash(data.new_password)
        await user.save()
        
        return {"message": "Password reset successfully"}
