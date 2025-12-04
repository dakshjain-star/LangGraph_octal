"""
LangGraph Task Management Chatbot - shim entrypoint.

This file is a minimal entrypoint that imports and runs the FastAPI
application defined in the `chatbot` package. The bulk of the
implementation lives in `chatbot/` modules to keep this file small.
"""
import os
import sys

# Keep original import path behavior for `dash_api`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'dash_api'))

from chatbot import api_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:api_app", host="0.0.0.0", port=8081, reload=True)
