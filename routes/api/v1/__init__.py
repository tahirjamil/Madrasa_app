from quart import Blueprint, jsonify, request
from utils.helpers.helpers import require_api_key
from quart_babel import gettext as _
from config import config
from utils.helpers.improved_funtions import send_json_response

api = Blueprint("api", __name__)

@api.before_request
# @require_api_key TODO: fix this
async def check():
    lang = request.accept_languages.best_match(["en", "bn", "ar"])
    if config.is_maintenance:
        response, status = send_json_response(_("System is under maintenance. Please try again later."), 503)
        response.update({"action": "maintenance"})
        return jsonify(response), status



# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401