"""Authentication service with JWT and password hashing."""
from datetime import datetime, timedelta
from typing import Optional, Dict
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication service for JWT and password management."""
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password."""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token."""
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(
                minutes=settings.access_token_expire_minutes
            )
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict) -> str:
        """Create a JWT refresh token."""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return encoded_jwt
    
    @staticmethod
    def create_password_reset_token(email: str) -> str:
        """Create a password reset token."""
        expire = datetime.utcnow() + timedelta(
            hours=settings.password_reset_token_expire_hours
        )
        to_encode = {
            "sub": email,
            "exp": expire,
            "type": "password_reset"
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm
        )
        return encoded_jwt
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[Dict]:
        """Verify and decode a JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm]
            )
            
            # Check token type
            if payload.get("type") != token_type:
                return None
            
            return payload
            
        except JWTError:
            return None
    
    @staticmethod
    def create_token_pair(user_id: str, email: str) -> Dict[str, str]:
        """Create both access and refresh tokens."""
        token_data = {"sub": user_id, "email": email}
        
        access_token = AuthService.create_access_token(token_data)
        refresh_token = AuthService.create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60
        }


# Convenience functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password."""
    return AuthService.verify_password(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return AuthService.get_password_hash(password)


def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create an access token."""
    return AuthService.create_access_token(data, expires_delta)


def create_refresh_token(data: Dict) -> str:
    """Create a refresh token."""
    return AuthService.create_refresh_token(data)


def verify_token(token: str, token_type: str = "access") -> Optional[Dict]:
    """Verify a token."""
    return AuthService.verify_token(token, token_type)


def create_token_pair(user_id: str, email: str) -> Dict[str, str]:
    """Create token pair."""
    return AuthService.create_token_pair(user_id, email)
