"""Tests for user endpoints."""
import pytest
from httpx import AsyncClient

from app.models.user import User, UserRole
from tests.conftest import get_auth_header


@pytest.mark.users
class TestUsers:
    """Test user endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_all_users(self, client: AsyncClient, test_user: User, user_token: str):
        """Test getting all users."""
        response = await client.get(
            "/api/v1/users/",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    @pytest.mark.asyncio
    async def test_get_user_by_id(self, client: AsyncClient, test_user: User, user_token: str):
        """Test getting user by ID."""
        response = await client.get(
            f"/api/v1/users/{test_user.id}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name
    
    @pytest.mark.asyncio
    async def test_update_own_user(self, client: AsyncClient, test_user: User, user_token: str):
        """Test updating own user."""
        response = await client.put(
            f"/api/v1/users/{test_user.id}",
            headers=get_auth_header(user_token),
            json={
                "name": "Updated Name",
                "company_name": "Updated Company"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["company_name"] == "Updated Company"
    
    @pytest.mark.asyncio
    async def test_update_user_role_as_admin(
        self, client: AsyncClient, test_user: User, admin_user: User, admin_token: str
    ):
        """Test admin updating user role."""
        response = await client.patch(
            f"/api/v1/users/{test_user.id}/role",
            headers=get_auth_header(admin_token),
            json={"role": "Admin"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "Admin"
    
    @pytest.mark.asyncio
    async def test_update_user_role_as_non_admin(
        self, client: AsyncClient, admin_user: User, user_token: str
    ):
        """Test non-admin trying to update role (should fail)."""
        response = await client.patch(
            f"/api/v1/users/{admin_user.id}/role",
            headers=get_auth_header(user_token),
            json={"role": "Member"}
        )
        
        assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_delete_user_as_admin(
        self, client: AsyncClient, test_user: User, admin_token: str
    ):
        """Test admin deleting user."""
        response = await client.delete(
            f"/api/v1/users/{test_user.id}",
            headers=get_auth_header(admin_token)
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_search_users(self, client: AsyncClient, test_user: User, user_token: str):
        """Test searching users."""
        response = await client.get(
            f"/api/v1/users/search?query={test_user.name[:5]}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
