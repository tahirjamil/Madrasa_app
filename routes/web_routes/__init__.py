from quart import Blueprint, render_template, request
from helpers import require_api_key
from config import config

web_routes = Blueprint('web_routes', __name__)

@web_routes.before_request
# @require_api_key TODO: fix this
async def check():
    if config.is_maintenance():
        return await render_template("maintenance.html"), 503

# Import routes from other modules to register them
from . import views # noqa: F401