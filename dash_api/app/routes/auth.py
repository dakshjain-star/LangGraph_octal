"""Authentication routes."""
from fastapi import APIRouter, Depends, status
from typing import List

from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse
)
from app.schemas.user import UserResponse
from app.controllers.auth_controller import AuthController
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account and return authentication tokens"
)
async def register(request: RegisterRequest):
    """
    Register a new user with the following information:
    - **name**: Full name of the user
    - **email**: Email address (must be unique)
    - **password**: Password (minimum 8 characters)
    - **company_name**: Name of the user's company
    
    Returns access and refresh tokens upon successful registration.
    """
    return await AuthController.register(request)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login user",
    description="Authenticate user and return tokens"
)
async def login(request: LoginRequest):
    """
    Authenticate a user with:
    - **email**: User's email address
    - **password**: User's password
    
    Returns access and refresh tokens upon successful authentication.
    """
    return await AuthController.login(request)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Get a new access token using a refresh token"
)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh the access token using a valid refresh token.
    
    - **refresh_token**: Valid refresh token
    
    Returns new access and refresh tokens.
    """
    return await AuthController.refresh_token(request)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current user",
    description="Get the authenticated user's information"
)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get the currently authenticated user's information.
    
    Requires authentication via Bearer token.
    """
    return await AuthController.get_current_user_info(current_user)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request password reset",
    description="Send password reset email to user"
)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Initiate password reset process:
    - **email**: Email address of the account
    
    Sends a password reset email if the email exists in the system.
    Always returns success for security reasons.
    """
    return await AuthController.forgot_password(request)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password",
    description="Reset user password using reset token"
)
async def reset_password(request: ResetPasswordRequest):
    """
    Reset password using a valid reset token:
    - **token**: Password reset token (from email)
    - **new_password**: New password (minimum 8 characters)
    
    Sets the new password if the token is valid.
    """
    return await AuthController.reset_password(request)
