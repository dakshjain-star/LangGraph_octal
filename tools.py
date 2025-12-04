"""
Compatibility shim: re-export from new modular chatbot_tools package.

This file exists for backwards compatibility with existing code that imports from tools.
New code should import directly from chatbot_tools instead.
"""
from chatbot_tools import tools, set_main_loop, run_async  # noqa: F401

__all__ = ["tools", "set_main_loop", "run_async"]
