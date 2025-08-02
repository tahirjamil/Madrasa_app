from quart import Blueprint, jsonify, request
from helpers import is_maintenance_mode, require_api_key
from quart_babel import gettext as _

user_routes = Blueprint("user_routes", __name__)

@user_routes.before_request
# @require_api_key TODO: fix this
async def check():
    lang = request.accept_languages.best_match(["en", "bn", "ar"])
    if is_maintenance_mode():
        return jsonify({"action": "maintenance", "message": _("System is under maintenance. Please try again later.")}), 503



# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401