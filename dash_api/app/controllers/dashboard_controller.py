"""Dashboard controller with business logic."""
from fastapi import HTTPException, status
from typing import Dict, List
from datetime import datetime

from app.models.task import Task, TaskStatus, TaskPriority
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.dashboard import DashboardStats
from app.schemas.project import ProjectResponse
from app.schemas.task import TaskResponse


class DashboardController:
    """Dashboard controller for handling dashboard operations."""
    
    @staticmethod
    async def get_dashboard_stats(current_user: User) -> DashboardStats:
        """Get aggregated dashboard statistics for current user."""
        today = datetime.utcnow().date()
        user_id = str(current_user.id)
        company_id = current_user.get_effective_company_id()
        
        # Use aggregation for efficiency
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "$or": [
                        {"assignee_id": user_id},
                        {"creator_id": user_id}
                    ]
                }
            },
            {
                "$facet": {
                    "completed": [
                        {"$match": {"status": TaskStatus.DONE}},
                        {"$count": "count"}
                    ],
                    "pending": [
                        {
                            "$match": {
                                "assignee_id": user_id,
                                "status": {"$ne": TaskStatus.DONE}
                            }
                        },
                        {"$count": "count"}
                    ],
                    "high_priority": [
                        {
                            "$match": {
                                "assignee_id": user_id,
                                "priority": TaskPriority.HIGH,
                                "status": {"$ne": TaskStatus.DONE}
                            }
                        },
                        {"$count": "count"}
                    ],
                    "in_progress": [
                        {
                            "$match": {
                                "assignee_id": user_id,
                                "status": TaskStatus.IN_PROGRESS
                            }
                        },
                        {"$count": "count"}
                    ]
                }
            }
        ]
        
        result = await Task.aggregate(pipeline).to_list()
        stats = result[0] if result else {}
        
        # Count overdue tasks manually (date comparison)
        overdue_tasks = await Task.find(
            Task.assignee_id == user_id,
            Task.company_id == company_id,
            Task.status != TaskStatus.DONE
        ).to_list()
        
        overdue_count = sum(1 for task in overdue_tasks if task.due_date and task.due_date < today)
        
        # Count active projects where user is involved
        active_projects_count = await Project.find(
            Project.owner_id == user_id,
            Project.company_id == company_id,
            Project.status == ProjectStatus.ACTIVE
        ).count()
        
        return DashboardStats(
            tasks_completed=stats.get("completed", [{}])[0].get("count", 0) if stats.get("completed") else 0,
            pending_tasks=stats.get("pending", [{}])[0].get("count", 0) if stats.get("pending") else 0,
            high_priority_tasks=stats.get("high_priority", [{}])[0].get("count", 0) if stats.get("high_priority") else 0,
            active_projects=active_projects_count,
            overdue_tasks=overdue_count,
            tasks_in_progress=stats.get("in_progress", [{}])[0].get("count", 0) if stats.get("in_progress") else 0
        )
    
    @staticmethod
    async def get_recent_projects(current_user: User, limit: int = 5) -> List[ProjectResponse]:
        """Get recent projects I own or am involved in."""
        user_id = str(current_user.id)
        company_id = current_user.get_effective_company_id()
        
        # Get projects owned by current user in their company
        projects = await Project.find(
            Project.owner_id == user_id,
            Project.company_id == company_id,
            Project.status == ProjectStatus.ACTIVE
        ).sort([("updated_at", -1)]).limit(limit).to_list()
        
        return [
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
            for project in projects
        ]
    
    @staticmethod
    async def get_my_pending_tasks(current_user: User, limit: int = 5) -> List[TaskResponse]:
        """Get my pending tasks (not done), ordered by due_date."""
        user_id = str(current_user.id)
        company_id = current_user.get_effective_company_id()
        today = datetime.utcnow().date()
        
        # Get tasks assigned to me that are not done in my company
        tasks = await Task.find(
            Task.assignee_id == user_id,
            Task.company_id == company_id,
            Task.status != TaskStatus.DONE
        ).sort([("due_date", 1)]).limit(limit).to_list()
        
        task_responses = []
        for task in tasks:
            is_overdue = False
            if task.due_date and task.due_date < today:
                is_overdue = True
            
            task_responses.append(
                TaskResponse(
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
                )
            )
        
        return task_responses
