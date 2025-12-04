# Dash SaaS API

A comprehensive FastAPI backend for the Dash SaaS project and task management application.

## Features

- 🔐 **JWT Authentication** - Secure token-based authentication with refresh tokens
- 👥 **User Management** - User registration, profiles, and role-based access control (Admin/Member/Viewer)
- 📋 **Task Management** - Full CRUD with advanced filtering, sorting, and search
- 📁 **Project Management** - Project organization with client tracking and status management
- 💬 **Comments** - Task commenting system
- 📊 **Dashboard Analytics** - Real-time statistics and aggregations
- 📧 **Email Service** - User invitations and password reset emails
- 🗄️ **MongoDB** - NoSQL database with async Motor driver
- ✅ **Comprehensive Testing** - Pytest with async support
- 📖 **Auto-generated API Docs** - Interactive Swagger UI and ReDoc

## Tech Stack

- **Framework**: FastAPI 0.109.0
- **Database**: MongoDB with Motor (async) and Beanie ODM
- **Authentication**: JWT with python-jose
- **Password Hashing**: Bcrypt
- **Email**: aiosmtplib
- **Testing**: Pytest + pytest-asyncio
- **Validation**: Pydantic v2

## Project Structure

```
dash_api/
├── app/
│   ├── __init__.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Environment configuration
│   ├── database/
│   │   ├── __init__.py
│   │   └── mongodb.py            # MongoDB connection
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py               # User document model
│   │   ├── project.py            # Project document model
│   │   ├── task.py               # Task document model
│   │   └── comment.py            # Comment document model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── auth.py               # Auth request/response schemas
│   │   ├── user.py               # User schemas
│   │   ├── project.py            # Project schemas
│   │   ├── task.py               # Task schemas
│   │   ├── comment.py            # Comment schemas
│   │   └── dashboard.py          # Dashboard schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py               # JWT & password hashing
│   │   └── email.py              # Email sending service
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py               # Auth dependencies
│   │   └── error_handler.py      # Global error handling
│   ├── controllers/
│   │   ├── __init__.py
│   │   ├── auth_controller.py
│   │   ├── user_controller.py
│   │   ├── project_controller.py
│   │   ├── task_controller.py
│   │   ├── comment_controller.py
│   │   └── dashboard_controller.py
│   └── routes/
│       ├── __init__.py
│       ├── auth.py
│       ├── users.py
│       ├── projects.py
│       ├── tasks.py
│       ├── comments.py
│       ├── dashboard.py
│       └── settings.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py               # Test fixtures
│   ├── test_auth.py
│   ├── test_users.py
│   ├── test_tasks.py
│   └── test_projects.py
├── main.py                        # FastAPI application entry point
├── requirements.txt
├── .env.example
├── .gitignore
├── pytest.ini
└── README.md
```

## Installation

### Prerequisites

- Python 3.9+
- MongoDB 5.0+
- pip or poetry

### Setup

1. **Clone the repository**
   ```bash
   cd dash_api
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   # Copy example env file
   copy .env.example .env  # Windows
   cp .env.example .env    # Linux/Mac
   
   # Edit .env and update:
   # - MONGODB_URL
   # - JWT_SECRET_KEY
   # - SMTP credentials
   ```

5. **Start MongoDB** (if not already running)
   ```bash
   # Using MongoDB locally
   mongod
   
   # Or using Docker
   docker run -d -p 27017:27017 --name mongodb mongo:latest
   ```

6. **Run the application**
   ```bash
   # Development mode with auto-reload
   uvicorn main:app --reload --host 0.0.0.0 --port 8001
   
   # Or using Python
   python main.py
   ```

7. **Access the API**
   - API: http://localhost:8001
   - Swagger UI: http://localhost:8001/docs
   - ReDoc: http://localhost:8001/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login (returns JWT)
- `POST /api/v1/auth/refresh` - Refresh access token
- `GET /api/v1/auth/me` - Get current user
- `POST /api/v1/auth/forgot-password` - Request password reset
- `POST /api/v1/auth/reset-password` - Reset password

### Users
- `GET /api/v1/users` - List all users (with filters)
- `GET /api/v1/users/{id}` - Get user by ID
- `PUT /api/v1/users/{id}` - Update user
- `DELETE /api/v1/users/{id}` - Delete user
- `POST /api/v1/users/invite` - Invite user by email

### Projects
- `GET /api/v1/projects` - List all projects (with filters)
- `GET /api/v1/projects/{id}` - Get project by ID
- `POST /api/v1/projects` - Create project
- `PUT /api/v1/projects/{id}` - Update project
- `DELETE /api/v1/projects/{id}` - Delete project
- `GET /api/v1/projects/{id}/tasks` - Get project tasks

### Tasks
- `GET /api/v1/tasks` - List all tasks (with filters)
- `GET /api/v1/tasks/{id}` - Get task by ID
- `POST /api/v1/tasks` - Create task
- `PUT /api/v1/tasks/{id}` - Update task
- `PATCH /api/v1/tasks/{id}/status` - Update task status
- `DELETE /api/v1/tasks/{id}` - Delete task
- `GET /api/v1/tasks/my` - Get my tasks
- `GET /api/v1/tasks/created-by-me` - Get tasks I created

### Comments
- `GET /api/v1/tasks/{task_id}/comments` - Get task comments
- `POST /api/v1/tasks/{task_id}/comments` - Add comment
- `PUT /api/v1/comments/{id}` - Update comment
- `DELETE /api/v1/comments/{id}` - Delete comment

### Dashboard
- `GET /api/v1/dashboard/stats` - Get dashboard statistics
- `GET /api/v1/dashboard/recent-projects` - Get recent projects
- `GET /api/v1/dashboard/my-tasks` - Get user's pending tasks

### Settings
- `GET /api/v1/settings` - Get user settings
- `PUT /api/v1/settings` - Update settings
- `POST /api/v1/settings/password` - Change password

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py

# Run tests by marker
pytest -m auth
pytest -m integration
```

## Environment Variables

See `.env.example` for all available configuration options.

Key variables:
- `MONGODB_URL` - MongoDB connection string
- `JWT_SECRET_KEY` - Secret key for JWT signing
- `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD` - Email configuration
- `CORS_ORIGINS` - Allowed frontend origins (default: http://localhost:3000)

## Authentication & Authorization

### Roles
- **Admin**: Full access to all resources
- **Member**: Can create/edit own tasks and projects
- **Viewer**: Read-only access

### Protected Routes
Most endpoints require authentication via JWT token in the `Authorization` header:
```
Authorization: Bearer <your_jwt_token>
```

## Development

### Code Style
- Follow PEP 8
- Use type hints
- Document functions with docstrings

### Database Indexes
The following indexes are created automatically:
- Users: email (unique)
- Tasks: assignee_id, creator_id, project_id, status, due_date
- Projects: owner_id, status
- Comments: task_id, user_id

## Deployment

### Production Checklist
- [ ] Change `JWT_SECRET_KEY` to a secure random string
- [ ] Set `DEBUG=False`
- [ ] Configure production MongoDB URL
- [ ] Set up SMTP credentials
- [ ] Configure CORS_ORIGINS to your frontend domain
- [ ] Set up SSL/TLS certificates
- [ ] Configure proper logging
- [ ] Set up monitoring (e.g., Sentry)

### Run with Gunicorn
```bash
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

### Docker (Optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Write tests
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License

## Support

For issues or questions, please open an issue on GitHub.
