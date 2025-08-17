from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

admin_routes = APIRouter()

# Set up templates for admin pages
templates = Jinja2Templates(directory="templates")

# Import routes from other modules to register them
from . import auth_admin  # noqa: F401
from . import views  # noqa: F401
from . import auxiliary  # noqa: F401