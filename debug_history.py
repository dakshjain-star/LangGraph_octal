"""
Debug script to check TaskHistory collection
"""
import asyncio
import os
import sys

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

async def debug_task_history():
    # Import database models
    from dash_api.app.models.task_history import TaskHistory
    from dash_api.app.models.task import Task
    from dash_api.app.database.mongodb import MongoDB
    
    # Initialize database
    await MongoDB.connect_db()
    
    print("=== DEBUGGING TASK HISTORY ===")
    
    # Get all TaskHistory entries
    all_history = await TaskHistory.find({}).to_list()
    print(f"Total TaskHistory entries: {len(all_history)}")
    
    if all_history:
        print("\n=== SAMPLE HISTORY ENTRIES ===")
        for i, entry in enumerate(all_history[:3]):  # Show first 3
            print(f"\nEntry {i+1}:")
            print(f"  ID: {entry.id}")
            print(f"  Task ID: {entry.task_id}")
            print(f"  Action: {entry.action}")
            print(f"  User Name: {entry.user_name}")
            print(f"  Company ID: {entry.company_id}")
            print(f"  Created: {entry.created_at}")
            print(f"  Field: {entry.field_name}")
            print(f"  Old Value: {entry.old_value}")
            print(f"  New Value: {entry.new_value}")
    
    # Check for the specific task "backend 502 error fixing"
    tasks = await Task.find({}).to_list()
    print(f"\n=== ALL TASKS ===")
    for task in tasks:
        print(f"Task: {task.title} (ID: {task.id})")
        
        # Check history for this task
        task_history = await TaskHistory.find({"task_id": str(task.id)}).to_list()
        print(f"  History entries: {len(task_history)}")
        
        if task.title and "502" in task.title:
            print(f"  *** FOUND TARGET TASK: {task.title} ***")
            print(f"      Task ID: {task.id}")
            print(f"      Company ID: {task.company_id}")
            
            # Try different query variations
            history1 = await TaskHistory.find({"task_id": str(task.id)}).to_list()
            history2 = await TaskHistory.find({"task_id": task.id}).to_list()  # Without str()
            history3 = await TaskHistory.find({"task_id": str(task.id), "company_id": task.company_id}).to_list()
            
            print(f"      Query 1 (str(task.id)): {len(history1)} entries")
            print(f"      Query 2 (task.id): {len(history2)} entries") 
            print(f"      Query 3 (with company_id): {len(history3)} entries")
            
            if history1:
                print(f"      Sample history entry:")
                h = history1[0]
                print(f"        Action: {h.action}")
                print(f"        User: {h.user_name}")
                print(f"        Created: {h.created_at}")

if __name__ == "__main__":
    asyncio.run(debug_task_history())