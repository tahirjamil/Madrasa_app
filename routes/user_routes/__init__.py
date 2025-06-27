from flask import Blueprint

user_routes = Blueprint("user_routes", __name__)

from . import auth
from . import payments
from . import core