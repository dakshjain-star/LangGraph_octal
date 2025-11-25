def chat_turn(user_input, thread_id="101"):
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\nUser: {user_input}")
    
    # Using 'values' to see the whole stream cleanly
    for event in app.stream({"messages": [HumanMessage(content=user_input)]}, config=config, stream_mode="values"):
        last_msg = event["messages"][-1]
        # Only print if it's new output (not the input we just sent)
        if last_msg.content and last_msg.type != "human":
             print(f"Bot: {last_msg.content}")

# Test Sequence
print("--- Starting Local Session ---")
chat_turn("login aarav@octal.com pass123") 
# Should see success message

chat_turn("What are my current tasks?") 
# Should trigger 'view_my_tasks' tool

chat_turn("Create a task 'Check Server Logs' for vivaan@octal.com with High priority")
# Should trigger 'create_task' tool