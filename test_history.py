"""
Test task history retrieval with the updated logic
"""
import asyncio
import os
import sys

# Add dash_api to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

async def test_task_history():
    from dash_api.app.database.mongodb import MongoDB
    from tools import _get_task_history_async
    
    # Initialize database
    await MongoDB.connect_db()
    
    print("Testing task history retrieval...")
    
    # Test with the known task name
    result = await _get_task_history_async(
        task_title="backend 502 error fixing",
        current_user_id="your-user-id",  # Replace with actual user ID if needed
        company_id="your-company-id"     # Replace with actual company ID if needed
    )
    
    print("Result:")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_task_history())