from quart import Blueprint, jsonify, request
from helpers import is_maintenance_mode, is_valid_api_key
from quart_babel import gettext as _

user_routes = Blueprint("user_routes", __name__)

@user_routes.before_request
async def check():
    lang = request.accept_languages.best_match(["en", "bn", "ar"])
    if is_maintenance_mode():
        return jsonify({"action": "maintenance", "message": _("System is under maintenance. Please try again later.")}), 503

    # Get API key from headers
    auth_header = request.headers.get('Authorization')
    api_key_header = request.headers.get('X-API-Key')
    
    # Check if API key is valid
    if auth_header and auth_header.startswith('Bearer '):
        api_key = auth_header.split(' ')[1]
    elif api_key_header:
        api_key = api_key_header
    else:
        return jsonify({'action': 'block', 'message': 'No API key provided'}), 401
    
    # Validate API key
    if not is_valid_api_key(api_key):
        return jsonify({'action': 'block', 'message': 'Invalid API key'}), 401


# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401