from fastapi import APIRouter

web_routes = APIRouter()

# TODO: Add require api key to all routes

# Import routes from other modules to register them
from .v1 import views # noqa: F401

__all__ = ["web_routes"]