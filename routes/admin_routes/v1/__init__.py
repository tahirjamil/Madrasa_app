from fastapi import APIRouter
from utils.helpers.fastapi_helpers import templates

admin_routes = APIRouter()

# Import routes from other modules to register them
from . import auth_admin  # noqa: F401
from . import views  # noqa: F401
from . import auxiliary  # noqa: F401