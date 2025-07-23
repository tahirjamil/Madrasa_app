from flask import Blueprint, render_template, request
from helpers import is_maintenance_mode, blocker

web_routes = Blueprint('web_routes', __name__)

@web_routes.before_request
def check():
    if is_maintenance_mode():
        return render_template("maintenance.html"), 503

    if blocker(request.remote_addr):
        return render_template("maintenance.html"), 503

# Import routes from other modules to register them
from . import views # noqa: F401