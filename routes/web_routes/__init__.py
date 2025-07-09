from flask import Blueprint

web_routes = Blueprint('web_routes', __name__, template_folder='../../templates/admin')

# Import routes from other modules to register them
from . import views # noqa: F401