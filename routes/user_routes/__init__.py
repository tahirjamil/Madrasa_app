from flask import Blueprint, jsonify, request
from helpers import is_maintenance_mode
from translations import t

user_routes = Blueprint("user_routes", __name__)

@user_routes.before_request
def check_maintenance():
    lang = request.accept_languages.best_match(["en", "bn", "ar"])
    if not is_maintenance_mode():
        return jsonify({"action": "maintenance", "message": t("maintenance_message", lang)}), 503

# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401