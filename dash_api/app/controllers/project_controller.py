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


class ProjectController:
    """Project controller for handling project operations."""
    
    @staticmethod
    async def get_all_projects(filter_data: ProjectFilter) -> Dict:
        """Get all projects with complex filtering."""
        query = {}
        
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
        
        # Get total count
        total = await Project.find(query).count()
        
        # Determine sort order
        sort_direction = 1 if filter_data.sort_order == "asc" else -1
        
        # Get projects with pagination and sorting
        projects = await Project.find(query)\
            .sort((filter_data.sort_by, sort_direction))\
            .skip(filter_data.skip)\
            .limit(filter_data.limit)\
            .to_list()
        
        # Get task counts for each project
        project_responses = []
        for project in projects:
            task_count = await Task.find(Task.project_id == str(project.id)).count()
            
            project_responses.append(
                ProjectResponse(
                    id=str(project.id),
                    name=project.name,
                    description=project.description,
                    status=project.status,
                    due_date=project.due_date,
                    owner_id=project.owner_id,
                    owner_name=project.owner_name,
                    client_name=project.client_name,
                    created_at=project.created_at,
                    updated_at=project.updated_at
                )
            )
        
        return {
            "projects": project_responses,
            "total": total,
            "skip": filter_data.skip,
            "limit": filter_data.limit
        }
    
    @staticmethod
    async def get_project_by_id(project_id: str) -> Dict:
        """Get a single project by ID with task count."""
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get task count
        task_count = await Task.find(Task.project_id == str(project.id)).count()
        
        project_response = ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
        
        return {
            **project_response.model_dump(),
            "task_count": task_count
        }
    
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
        
        # Create project
        project = Project(
            name=data.name,
            description=data.description,
            status=data.status,
            due_date=data.due_date,
            owner_id=owner_id,
            owner_name=owner.name,
            client_name=data.client_name
        )
        
        await project.insert()
        
        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
    
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
        
        for field, value in update_data.items():
            setattr(project, field, value)
        
        project.updated_at = datetime.utcnow()
        await project.save()
        
        return ProjectResponse(
            id=str(project.id),
            name=project.name,
            description=project.description,
            status=project.status,
            due_date=project.due_date,
            owner_id=project.owner_id,
            owner_name=project.owner_name,
            client_name=project.client_name,
            created_at=project.created_at,
            updated_at=project.updated_at
        )
    
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
            due_date=project.due_date,
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
        
        # Check permissions - owner or admin can delete
        if project.owner_id != str(current_user.id) and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this project"
            )
        
        # Delete project
        await project.delete()
        
        return {"message": "Project deleted successfully"}
    
    @staticmethod
    async def get_project_tasks(project_id: str, skip: int = 0, limit: int = 50) -> Dict:
        """Get all tasks for a project."""
        # Check if project exists
        project = await Project.get(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        # Get total task count
        total = await Task.find(Task.project_id == project_id).count()
        
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
            
            task_responses.append({
                "id": str(task.id),
                "title": task.title,
                "description": task.description,
                "status": task.status,
                "priority": task.priority,
                "due_date": task.due_date,
                "assignee_id": task.assignee_id,
                "assignee_name": task.assignee_name,
                "assignee_avatar": task.assignee_avatar,
                "creator_id": task.creator_id,
                "project_id": task.project_id,
                "project_name": task.project_name,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "is_overdue": is_overdue
            })
        
        return {
            "tasks": task_responses,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    
    @staticmethod
    async def get_project_owners() -> List[Dict[str, str]]:
        """Get unique list of project owners for filter dropdown."""
        # Get all unique owner_id and owner_name combinations
        pipeline = [
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
