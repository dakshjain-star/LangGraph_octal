# Dash API - Quick Start Guide

## 🚀 Quick Setup Instructions

### 1. Navigate to the API directory
```powershell
cd dash_api
```

### 2. Create and activate virtual environment
```powershell
# Create virtual environment
python -m venv venv

# Activate it (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies
```powershell
pip install -r requirements.txt
```

### 4. Setup MongoDB
Make sure MongoDB is running on your system:

**Option A: Local MongoDB**
```powershell
# If MongoDB is installed locally, start it
mongod
```

**Option B: MongoDB with Docker**
```powershell
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

### 5. Configure environment variables
```powershell
# Copy the example env file
copy .env.example .env

# Edit .env file and update:
# - JWT_SECRET_KEY (use a secure random string)
# - SMTP credentials (if you want email functionality)
# - MongoDB URL (if different from default)
```

### 6. Run the application
```powershell
# Development mode with auto-reload
python main.py

# Or using uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 7. Access the API
- **API Base URL**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/redoc

## 📝 Testing the API

### Run all tests
```powershell
pytest
```

### Run specific test files
```powershell
pytest tests/test_auth.py
pytest tests/test_users.py
pytest tests/test_tasks.py
```

### Run with coverage
```powershell
pytest --cov=app --cov-report=html
```

## 🔑 First Steps After Setup

1. **Register a user** via POST `/api/v1/auth/register`
2. **Login** via POST `/api/v1/auth/login` to get JWT token
3. **Use the token** in Authorization header: `Bearer <your_token>`
4. **Explore the API** using the interactive docs at `/docs`

## 🔧 Environment Variables

Key variables to configure in `.env`:

```env
# Database
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=dash_saas

# JWT Secret (CHANGE THIS!)
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production

# CORS (frontend URL - running on port 3000)
CORS_ORIGINS=http://localhost:3000

# Email (optional, for invitations and password reset)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

## 📂 Project Structure Overview

```
dash_api/
├── app/
│   ├── models/         # MongoDB document models (User, Project, Task, Comment)
│   ├── schemas/        # Pydantic request/response schemas
│   ├── controllers/    # Business logic layer
│   ├── routes/         # API endpoints
│   ├── services/       # Auth, Email services
│   ├── middleware/     # Auth, Error handling
│   ├── config/         # Settings and configuration
│   └── database/       # MongoDB connection
├── tests/              # Pytest tests
├── main.py             # FastAPI app entry point
└── requirements.txt    # Python dependencies
```

## 🌐 API Endpoints Summary

### Authentication (`/api/v1/auth`)
- `POST /register` - Register new user
- `POST /login` - Login
- `POST /refresh` - Refresh token
- `GET /me` - Get current user
- `POST /forgot-password` - Request password reset
- `POST /reset-password` - Reset password

### Users (`/api/v1/users`)
- `GET /` - List all users
- `GET /{id}` - Get user by ID
- `PUT /{id}` - Update user
- `POST /invite` - Invite user
- And more...

### Projects (`/api/v1/projects`)
- `GET /` - List all projects
- `POST /` - Create project
- `GET /{id}` - Get project
- `PUT /{id}` - Update project
- And more...

### Tasks (`/api/v1/tasks`)
- `GET /` - List all tasks (with filters)
- `POST /` - Create task
- `GET /{id}` - Get task
- `PUT /{id}` - Update task
- `GET /my` - Get my tasks
- `GET /stats` - Get statistics
- And more...

### Dashboard (`/api/v1/dashboard`)
- `GET /stats` - Get dashboard statistics
- `GET /recent-projects` - Get recent projects
- `GET /my-tasks` - Get my pending tasks

## 🔐 Authentication Flow

1. Register or login to get access token
2. Include token in requests:
   ```
   Authorization: Bearer <access_token>
   ```
3. Token expires in 30 minutes (configurable)
4. Use refresh token to get new access token

## 🎯 Next Steps

1. **Connect Frontend**: Update dash_saas frontend to call these API endpoints
2. **Customize**: Modify models, schemas, or business logic as needed
3. **Deploy**: Follow deployment guide in README.md for production

## 📚 Full Documentation

See `README.md` for comprehensive documentation including:
- Complete API endpoint list
- Deployment instructions
- Security best practices
- Troubleshooting guide

---

**Happy Coding! 🎉**

For questions or issues, check the logs or API documentation at `/docs`.
