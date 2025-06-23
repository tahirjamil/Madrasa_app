from flask import Blueprint

admin_routes = Blueprint('admin_routes', __name__, template_folder='../../templates/admin')

# Import routes from other modules to register them
from . import auth
from . import views
from . import notices_admin