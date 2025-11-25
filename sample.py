import pymongo
import bcrypt
from datetime import datetime
from bson.objectid import ObjectId

# Connect to MongoDB (Ensure Mongo is running locally)
client = pymongo.MongoClient("mongodb+srv://octaldaksh:octal123@cluster0.5xt6n.mongodb.net/")
db = client["db_octal"]

# Clear existing to avoid duplicates for this demo
db.users.drop()
db.tasks.drop()

def hash_pass(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

# --- 1. Create 6 Sample Users ---
users_data = [
    {"first_name": "Aarav", "last_name": "Sharma", "email": "aarav@octal.com", "password": hash_pass("pass123"), "gender": "M"},
    {"first_name": "Vivaan", "last_name": "Gupta", "email": "vivaan@octal.com", "password": hash_pass("pass123"), "gender": "M"},
    {"first_name": "Diya", "last_name": "Singh", "email": "diya@octal.com", "password": hash_pass("pass123"), "gender": "F"},
    {"first_name": "Isha", "last_name": "Verma", "email": "isha@octal.com", "password": hash_pass("pass123"), "gender": "F"},
    {"first_name": "Rohan", "last_name": "Mehta", "email": "rohan@octal.com", "password": hash_pass("pass123"), "gender": "M"},
    {"first_name": "Ananya", "last_name": "Iyer", "email": "ananya@octal.com", "password": hash_pass("pass123"), "gender": "F"},
]

# Insert and add timestamps/IDs
for user in users_data:
    user['timestamp'] = datetime.now()
    
result_users = db.users.insert_many(users_data)
user_ids = result_users.inserted_ids # Save IDs to map to tasks

print("Users Created:", [str(id) for id in user_ids])

# --- 2. Create 3 Sample Tasks (Linked via Foreign Key) ---
# Logic: User 0 assigns to User 1, User 2 assigns to User 3, etc.

tasks_data = [
    {
        "title": "Fix Login Bug",
        "description": "Login button crashes on Safari.",
        "priority": "High",
        "start_date": "2023-10-25",
        "end_date": "2023-10-27",
        "assigned_by": user_ids[0], # Aarav
        "assignee": user_ids[1],    # Vivaan
    },
    {
        "title": "Update Homepage UI",
        "description": "Change banner colors to blue theme.",
        "priority": "Medium",
        "start_date": "2023-11-01",
        "end_date": "2023-11-05",
        "assigned_by": user_ids[0], # Aarav
        "assignee": user_ids[1],    # Vivaan
    },
    {
        "title": "Database Migration",
        "description": "Move user data to new cluster.",
        "priority": "Critical",
        "start_date": "2023-10-30",
        "end_date": "2023-11-10",
        "assigned_by": user_ids[2], # Diya
        "assignee": user_ids[3],    # Isha
    }
]

for task in tasks_data:
    task['timestamp'] = datetime.now()

db.tasks.insert_many(tasks_data)
print("Tasks Created with Foreign Key Relationships.")