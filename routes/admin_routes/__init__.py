from quart import Blueprint

admin_routes = Blueprint('admin_routes', __name__, template_folder='../../templates/admin')

# Import routes from other modules to register them
from . import auth_admin  # noqa: F401
from . import views  # noqa: F401
from . import auxiliary  # noqa: F401