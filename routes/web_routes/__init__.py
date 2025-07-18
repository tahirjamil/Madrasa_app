import os
from flask import Blueprint, render_template

web_routes = Blueprint('web_routes', __name__)

@web_routes.before_request
def check_maintenance():
    if os.getenv("MAINTENANCE_MODE", False):
        return render_template("maintenance.html"), 503

# Import routes from other modules to register them
from . import views # noqa: F401