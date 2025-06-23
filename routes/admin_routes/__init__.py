from flask import Blueprint

from . import auth, views

admin_blueprint = Blueprint('admin', __name__)

# Routes
admin_blueprint.add_url_rule('/', view_func=views.dashboard)
admin_blueprint.add_url_rule('/login', view_func=auth.login, methods=['GET', 'POST'])
admin_blueprint.add_url_rule('/logout', view_func=auth.logout)
admin_blueprint.add_url_rule('/members', view_func=views.members)
admin_blueprint.add_url_rule('/notice', view_func=views.notice)
admin_blueprint.add_url_rule('/routine', view_func=views.routine)
admin_blueprint.add_url_rule('/events', view_func=views.events)
admin_blueprint.add_url_rule('/exam_results', view_func=views.exam_results)
admin_blueprint.add_url_rule('/madrasha_pictures', view_func=views.madrasha_pictures)
