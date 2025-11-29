"""Project controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List, Optional
import re
from datetime import datetime

from app.models.project import Project, ProjectStatus
from app.models.user import User, UserRole
from app.models.task import Task
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectStatusUpdate,
    ProjectResponse, ProjectFilter
)
from app.schemas.task import TaskResponse
from app.services.websocket import (
    notify_project_created, notify_project_updated, notify_project_deleted
)


class ProjectController:
    """Project controller for handling project operations."""
    
    @staticmethod
    async def get_all_projects(filter_data: ProjectFilter, current_user: User = None) -> List[ProjectResponse]:
        """Get all projects with complex filtering."""
        query = {}
        
        # Filter by company - users can only see projects in their own company
        if current_user:
            effective_company_id = current_user.get_effective_company_id()
            if effective_company_id:
                query["company_id"] = effective_company_id
            else:
                # If no company, return empty list (shouldn't see any projects)
                return []
        
        # Apply filters
        if filter_data.status:
            query["status"] = {"$in": filter_data.status}
        
        if filter_data.owner_id:
            query["owner_id"] = filter_data.owner_id
        
        if filter_data.client_name:
            client_regex = re.compile(re.escape(filter_data.client_name), re.IGNORECASE)
            query["client_name"] = client_regex
        
        if filter_data.search:
            # Search in name and description
            search_regex = re.compile(re.escape(filter_data.search), re.IGNORECASE)
            query["$or"] = [
                {"name": search_regex},
                {"description": search_regex}
            ]
        
        # Determine sort order
        sort_direction = 1 if filter_data.sort_order == "asc" else -1
        
        # Get projects with pagination and sorting
        projects = await Project.find(query)\
            .sort((filter_data.sort_by, sort_direction))\
            .skip(filter_data.skip)\
            .limit(filter_data.limit)\
            .to_list()
        
        # Build project responses
        project_responses = []
        for project in projects:
            project_responses.append(
                ProjectResponse(
                    id=str(project.id),
                    name=project.name,
                    description=project.description,
                    status=project.status,
                    due_date=project.due_date.date() if project.due_date else None,
                    owner_id=project.owner_id,
                    owner_name=project.owner_name,
                    client_name=project.client_name,
                    created_at=project.created_at,
                    updated_at=project.updated_at
                )
            )
        
        return project_responses
    
    @staticmethod
    async def get_project_by_id(project_id: str, current_user: User = None) -> ProjectResponse:
        """Get a single project by ID."""
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check company access
        if current_user and project.company_id != current_user.get_effective_company_id():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this project"
            )
        
        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date.date() if project.due_date else None,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
    
    @staticmethod
    async def create_project(data: ProjectCreate, current_user: User) -> ProjectResponse:
        """Create a new project."""
        # Auto-set owner from current user if not provided
        owner_id = data.owner_id if data.owner_id else str(current_user.id)
        
        # Get owner information
        owner = await User.get(owner_id)
        if not owner:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Owner user not found"
            )
        
        # Convert date to datetime for MongoDB storage
        due_date_dt = None
        if data.due_date:
            due_date_dt = datetime.combine(data.due_date, datetime.min.time())
        
        # Create project
        project = Project(
            name=data.name,
            description=data.description,
            status=data.status,
            due_date=due_date_dt,
            owner_id=owner_id,
            owner_name=owner.name,
            company_id=current_user.get_effective_company_id(),
            company_name=current_user.current_company_name,
            client_name=data.client_name
        )
        
        await project.insert()
        
        project_response = ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date.date() if project.due_date else None,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
        
        # Send WebSocket notification
        project_data = project_response.model_dump()
        # Convert datetime objects to ISO strings for JSON serialization
        if project_data.get('due_date'):
            project_data['due_date'] = str(project_data['due_date'])
        if project_data.get('created_at'):
            project_data['created_at'] = project_data['created_at'].isoformat() if hasattr(project_data['created_at'], 'isoformat') else str(project_data['created_at'])
        if project_data.get('updated_at'):
            project_data['updated_at'] = project_data['updated_at'].isoformat() if hasattr(project_data['updated_at'], 'isoformat') else str(project_data['updated_at'])
        
        await notify_project_created(project_data, project.company_id, str(current_user.id))
        
        return project_response
    
    @staticmethod
    async def update_project(project_id: str, data: ProjectUpdate, current_user: User) -> ProjectResponse:
        """Update project information."""
        # Check if project exists
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check company access - users can only update projects in their own company
        if project.company_id != current_user.get_effective_company_id():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this project"
            )
        
        # Check permissions - owner or admin can update
        if project.owner_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this project"
            )
        
        # Update fields
        update_data = data.model_dump(exclude_unset=True)
        
        # If owner_id is being changed, update owner_name too
        if "owner_id" in update_data and update_data["owner_id"]:
            owner = await User.get(update_data["owner_id"])
            if not owner:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="New owner user not found"
                )
            project.owner_id = update_data["owner_id"]
            project.owner_name = owner.name
            update_data.pop("owner_id")
        
        # Convert due_date from date to datetime if present
        if "due_date" in update_data and update_data["due_date"]:
            update_data["due_date"] = datetime.combine(update_data["due_date"], datetime.min.time())
        
        for field, value in update_data.items():
            setattr(project, field, value)
        
        project.updated_at = datetime.utcnow()
        await project.save()
        
        project_response = ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date.date() if project.due_date else None,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
        
        # Send WebSocket notification
        project_data = project_response.model_dump()
        if project_data.get('due_date'):
            project_data['due_date'] = str(project_data['due_date'])
        if project_data.get('created_at'):
            project_data['created_at'] = project_data['created_at'].isoformat() if hasattr(project_data['created_at'], 'isoformat') else str(project_data['created_at'])
        if project_data.get('updated_at'):
            project_data['updated_at'] = project_data['updated_at'].isoformat() if hasattr(project_data['updated_at'], 'isoformat') else str(project_data['updated_at'])
        
        await notify_project_updated(project_data, project.company_id, str(current_user.id))
        
        return project_response
    
    @staticmethod
    async def update_project_status(project_id: str, data: ProjectStatusUpdate, current_user: User) -> ProjectResponse:
        """Update project status."""
        # Check if project exists
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check company access - users can only update projects in their own company
        if project.company_id != current_user.get_effective_company_id():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this project"
            )
        
        # Check permissions - owner or admin can update
        if project.owner_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this project"
            )
        
        # Update status
        project.status = data.status
        project.updated_at = datetime.utcnow()
        await project.save()
        
        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date.date() if project.due_date else None,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
    
    @staticmethod
    async def delete_project(project_id: str, current_user: User) -> Dict:
        """Delete a project."""
        # Check if project exists
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Check company access - users can only delete projects in their own company
        if project.company_id != current_user.get_effective_company_id():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this project"
            )
        
        # Check permissions - owner or admin can delete
        if project.owner_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this project"
            )
        
        # Update all tasks associated with this project to have no project
        from app.models.task import Task
        tasks = await Task.find(Task.project_id == project_id).to_list()
        for task in tasks:
            task.project_id = None
            task.project_name = None
            await task.save()
        
        # Store company_id before deletion for notification
        company_id = project.company_id
        
        # Delete project
        await project.delete()
        
        # Send WebSocket notification
        await notify_project_deleted(project_id, company_id, str(current_user.id))
        
        return {"message": "Project deleted successfully"}
    
    @staticmethod
    async def get_project_tasks(project_id: str, skip: int = 0, limit: int = 50) -> List[TaskResponse]:
        """Get all tasks for a project."""
        # Check if project exists
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get tasks with pagination
        tasks = await Task.find(Task.project_id == project_id)\
            .sort([("created_at", -1)])\
            .skip(skip)\
            .limit(limit)\
            .to_list()
        
        # Check for overdue tasks
        today = datetime.utcnow().date()
        task_responses = []
        for task in tasks:
            is_overdue = False
            if task.due_date and task.due_date < today and task.status.value != "Done":
                is_overdue = True
            
            task_responses.append(TaskResponse(
                id=str(task.id),
                title=task.title,
                description=task.description,
                status=task.status,
                priority=task.priority,
                due_date=task.due_date,
                assignee_id=task.assignee_id,
                assignee_name=task.assignee_name,
                assignee_avatar=task.assignee_avatar,
                creator_id=task.creator_id,
                project_id=task.project_id,
                project_name=task.project_name,
                created_at=task.created_at,
                updated_at=task.updated_at,
                is_overdue=is_overdue
            ))
        
        return task_responses
    
    @staticmethod
    async def get_project_owners(current_user: User = None) -> List[Dict[str, str]]:
        """Get unique list of project owners for filter dropdown."""
        # Build match stage with company filter
        match_stage = {}
        if current_user and current_user.get_effective_company_id():
            match_stage["company_id"] = current_user.get_effective_company_id()
        
        # Get all unique owner_id and owner_name combinations
        pipeline = [
            {
                "$match": match_stage
            },
            {
                "$group": {
                    "_id": "$owner_id",
                    "owner_name": {"$first": "$owner_name"}
                }
            },
            {
                "$project": {
                    "owner_id": "$_id",
                    "owner_name": 1,
                    "_id": 0
                }
            },
            {
                "$sort": {"owner_name": 1}
            }
        ]
        
        owners = await Project.aggregate(pipeline).to_list()
        
        return owners
