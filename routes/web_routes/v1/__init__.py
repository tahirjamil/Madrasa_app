from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from config import config

web_routes = APIRouter()

# Set up templates (will be configured in main app)
templates = Jinja2Templates(directory="templates")

# Note: Middleware should be added to the main app, not to routers
# The maintenance mode check will be handled by dependencies in individual routes

# Import routes from other modules to register them
from . import views # noqa: F401