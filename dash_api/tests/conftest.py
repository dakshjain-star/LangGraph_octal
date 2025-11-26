"""Test configuration and fixtures."""
import pytest
import asyncio
from typing import Generator, AsyncGenerator
from httpx import AsyncClient
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from faker import Faker

from main import app
from app.config import settings
from app.models.user import User, UserRole, UserStatus
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.comment import Comment
from app.services.auth import get_password_hash, create_token_pair

fake = Faker()

# Test database name
TEST_DB_NAME = "dash_saas_test"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def mongodb_client() -> AsyncGenerator:
    """Create MongoDB client for tests."""
    client = AsyncIOMotorClient(settings.mongodb_url)
    yield client
    client.close()


@pytest.fixture(scope="function")
async def db(mongodb_client):
    """Initialize test database."""
    database = mongodb_client[TEST_DB_NAME]
    
    # Initialize Beanie
    await init_beanie(
        database=database,
        document_models=[User, Project, Task, Comment]
    )
    
    yield database
    
    # Clean up after test
    await database.client.drop_database(TEST_DB_NAME)


@pytest.fixture(scope="function")
async def client(db) -> AsyncGenerator:
    """Create async HTTP client for testing."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def test_user(db) -> User:
    """Create a test user."""
    user = User(
        name=fake.name(),
        email=fake.email(),
        password_hash=get_password_hash("TestPassword123!"),
        company_name=fake.company(),
        status=UserStatus.ACTIVE,
        role=UserRole.MEMBER
    )
    await user.insert()
    return user


@pytest.fixture
async def admin_user(db) -> User:
    """Create an admin user."""
    user = User(
        name="Admin User",
        email="admin@test.com",
        password_hash=get_password_hash("AdminPass123!"),
        company_name=fake.company(),
        status=UserStatus.ACTIVE,
        role=UserRole.ADMIN
    )
    await user.insert()
    return user


@pytest.fixture
async def viewer_user(db) -> User:
    """Create a viewer user."""
    user = User(
        name="Viewer User",
        email="viewer@test.com",
        password_hash=get_password_hash("ViewerPass123!"),
        company_name=fake.company(),
        status=UserStatus.ACTIVE,
        role=UserRole.VIEWER
    )
    await user.insert()
    return user


@pytest.fixture
def user_token(test_user: User) -> str:
    """Generate JWT token for test user."""
    tokens = create_token_pair(str(test_user.id), test_user.email)
    return tokens["access_token"]


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """Generate JWT token for admin user."""
    tokens = create_token_pair(str(admin_user.id), admin_user.email)
    return tokens["access_token"]


@pytest.fixture
async def test_project(db, test_user: User) -> Project:
    """Create a test project."""
    project = Project(
        name=fake.catch_phrase(),
        description=fake.text(),
        status=ProjectStatus.ACTIVE,
        owner_id=str(test_user.id),
        owner_name=test_user.name,
        client_name=fake.company()
    )
    await project.insert()
    return project


@pytest.fixture
async def test_task(db, test_user: User, test_project: Project) -> Task:
    """Create a test task."""
    task = Task(
        title=fake.sentence(),
        description=fake.text(),
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        assignee_id=str(test_user.id),
        assignee_name=test_user.name,
        creator_id=str(test_user.id),
        project_id=str(test_project.id),
        project_name=test_project.name
    )
    await task.insert()
    return task


@pytest.fixture
async def test_comment(db, test_task: Task, test_user: User) -> Comment:
    """Create a test comment."""
    comment = Comment(
        task_id=str(test_task.id),
        user_id=str(test_user.id),
        user_name=test_user.name,
        content=fake.text()
    )
    await comment.insert()
    return comment


def get_auth_header(token: str) -> dict:
    """Helper function to create authorization header."""
    return {"Authorization": f"Bearer {token}"}
