import pymongo
from pydantic import BaseModel, ConfigDict
from typing import Optional, Any
from datetime import datetime
from bson.objectid import ObjectId

# --- Database Connection ---
MONGODB_URI = "mongodb+srv://octaldaksh:octal123@cluster0.5xt6n.mongodb.net/"
client = pymongo.MongoClient(MONGODB_URI)
db = client["db_octal"]

# --- Pydantic Schemas ---
class User(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    email: str
    password: bytes  # Hashed password
    first_name: str
    last_name: str

class Task(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    title: str
    description: Optional[str] = ""
    priority: Optional[str] = "Normal"
    start_date: str
    end_date: str
    assigned_by: Any  # ObjectId
    assignee: Any  # ObjectId
    timestamp: datetime

class Project(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    description: Optional[str] = ""
    client_name: str
    owner_name: str
    assignees: list[Any] = []  # List of ObjectIds

class Company(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    owner_name: str
    projects: list[Any] = []  # List of ObjectIds
    members: list[Any] = []  # List of ObjectIds
