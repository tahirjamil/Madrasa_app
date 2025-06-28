from flask import Blueprint

user_routes = Blueprint("user_routes", __name__)

# Import routes from other modules to register them
from . import auth  # noqa: F401
from . import payments  # noqa: F401
from . import core  # noqa: F401
# from . import payments_shurjopay