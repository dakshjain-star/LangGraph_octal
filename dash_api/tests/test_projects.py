"""Tests for project endpoints."""
import pytest
from httpx import AsyncClient
from datetime import date, timedelta

from app.models.user import User
from app.models.project import Project, ProjectStatus
from tests.conftest import get_auth_header


@pytest.mark.projects
class TestProjects:
    """Test project endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_all_projects(
        self, client: AsyncClient, test_project: Project, user_token: str
    ):
        """Test getting all projects."""
        response = await client.get(
            "/api/v1/projects/",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    @pytest.mark.asyncio
    async def test_get_project_by_id(
        self, client: AsyncClient, test_project: Project, user_token: str
    ):
        """Test getting project by ID."""
        response = await client.get(
            f"/api/v1/projects/{test_project.id}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_project.name
        assert "task_count" in data
    
    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient, test_user: User, user_token: str):
        """Test creating a project."""
        response = await client.post(
            "/api/v1/projects/",
            headers=get_auth_header(user_token),
            json={
                "name": "New Project",
                "description": "Project description",
                "client_name": "Test Client",
                "owner_id": str(test_user.id),
                "status": "Active",
                "due_date": str(date.today() + timedelta(days=30))
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Project"
        assert data["owner_name"] == test_user.name
    
    @pytest.mark.asyncio
    async def test_update_project(
        self, client: AsyncClient, test_project: Project, user_token: str
    ):
        """Test updating a project."""
        response = await client.put(
            f"/api/v1/projects/{test_project.id}",
            headers=get_auth_header(user_token),
            json={
                "name": "Updated Project Name",
                "description": "Updated description"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Project Name"
    
    @pytest.mark.asyncio
    async def test_update_project_status(
        self, client: AsyncClient, test_project: Project, user_token: str
    ):
        """Test updating project status."""
        response = await client.patch(
            f"/api/v1/projects/{test_project.id}/status",
            headers=get_auth_header(user_token),
            json={"status": "Archived"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Archived"
    
    @pytest.mark.asyncio
    async def test_get_project_tasks(
        self, client: AsyncClient, test_project: Project, test_task, user_token: str
    ):
        """Test getting project tasks."""
        response = await client.get(
            f"/api/v1/projects/{test_project.id}/tasks",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_delete_project(
        self, client: AsyncClient, test_project: Project, user_token: str
    ):
        """Test deleting a project."""
        response = await client.delete(
            f"/api/v1/projects/{test_project.id}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_project_owners(self, client: AsyncClient, test_project: Project, user_token: str):
        """Test getting unique project owners."""
        response = await client.get(
            "/api/v1/projects/owners",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
