from fastapi import APIRouter

web_routes = APIRouter()

# Note: Middleware should be added to the main app, not to routers
# The maintenance mode check will be handled by dependencies in individual routes

# Import routes from other modules to register them
from .v1 import views # noqa: F401

__all__ = ["web_routes"]