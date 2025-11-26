"""Tests for task endpoints."""
import pytest
from httpx import AsyncClient
from datetime import date, timedelta

from app.models.user import User
from app.models.project import Project
from app.models.task import Task, TaskStatus, TaskPriority
from tests.conftest import get_auth_header


@pytest.mark.tasks
class TestTasks:
    """Test task endpoints."""
    
    @pytest.mark.asyncio
    async def test_get_all_tasks(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test getting all tasks."""
        response = await client.get(
            "/api/v1/tasks/",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    @pytest.mark.asyncio
    async def test_get_task_by_id(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test getting task by ID."""
        response = await client.get(
            f"/api/v1/tasks/{test_task.id}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == test_task.title
        assert "comments" in data
    
    @pytest.mark.asyncio
    async def test_create_task(
        self, client: AsyncClient, test_user: User, test_project: Project, user_token: str
    ):
        """Test creating a task."""
        response = await client.post(
            "/api/v1/tasks/",
            headers=get_auth_header(user_token),
            json={
                "title": "New Task",
                "description": "Task description",
                "priority": "High",
                "status": "To Do",
                "assignee_id": str(test_user.id),
                "project_id": str(test_project.id),
                "due_date": str(date.today() + timedelta(days=7))
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Task"
        assert data["assignee_name"] == test_user.name
        assert data["project_name"] == test_project.name
    
    @pytest.mark.asyncio
    async def test_update_task(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test updating a task."""
        response = await client.put(
            f"/api/v1/tasks/{test_task.id}",
            headers=get_auth_header(user_token),
            json={
                "title": "Updated Task Title",
                "priority": "High"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Task Title"
        assert data["priority"] == "High"
    
    @pytest.mark.asyncio
    async def test_update_task_status(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test updating task status."""
        response = await client.patch(
            f"/api/v1/tasks/{test_task.id}/status",
            headers=get_auth_header(user_token),
            json={"status": "Done"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Done"
    
    @pytest.mark.asyncio
    async def test_get_my_tasks(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test getting my tasks."""
        response = await client.get(
            "/api/v1/tasks/my",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_task_stats(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test getting task statistics."""
        response = await client.get(
            "/api/v1/tasks/stats",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "tasks_completed" in data
        assert "pending_tasks" in data
        assert "high_priority_tasks" in data
    
    @pytest.mark.asyncio
    async def test_delete_task(self, client: AsyncClient, test_task: Task, user_token: str):
        """Test deleting a task."""
        response = await client.delete(
            f"/api/v1/tasks/{test_task.id}",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_filter_tasks_by_status(
        self, client: AsyncClient, test_task: Task, user_token: str
    ):
        """Test filtering tasks by status."""
        response = await client.get(
            "/api/v1/tasks/?status=To Do",
            headers=get_auth_header(user_token)
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        for task in data:
            assert task["status"] == "To Do"
