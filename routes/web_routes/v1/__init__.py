from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import config

web_routes = APIRouter()

# Set up templates (will be configured in main app)
templates = Jinja2Templates(directory="templates")

# Custom URL generation function for templates
def url_for(route_name: str, **kwargs):
    """Custom URL generation function for templates"""
    # Map route names to their paths
    route_map = {
        "home": "/",
        "donate": "/donate", 
        "contact": "/contact",
        "privacy": "/privacy",
        "terms": "/terms"
    }
    
    if route_name in route_map:
        return route_map[route_name]
    else:
        # Fallback to route name as path
        return f"/{route_name}"

# Note: Middleware should be added to the main app, not to routers
# The maintenance mode check will be handled by dependencies in individual routes

# Import routes from other modules to register them
from . import views # noqa: F401