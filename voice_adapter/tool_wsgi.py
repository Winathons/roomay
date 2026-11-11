"""WSGI entry point for the Vapi caller-intent endpoint.

Deploy as a separate WSGI service using ``voice_adapter.tool_wsgi:application``.
Configuration is read from server environment at process startup.
"""

from .intent_tools import ToolConfig, create_tool_app


application = create_tool_app(ToolConfig.from_environment())
