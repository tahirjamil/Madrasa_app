from flask import Flask, render_template, session, request
from flask_cors import CORS
from database import create_tables
from waitress import serve
import os
from datetime import datetime
from config import Config
from dotenv import load_dotenv

# API Routes
from routes.api.auth import api_auth_routes
from routes.api.payments import payment_routes
from routes.api.additionals import other_routes

# Web Routes
from routes.admin_routes import admin_routes

app = Flask(__name__)
CORS(app)
load_dotenv()

# In-memory log of the last 100 requests
requests_log = []

@app.before_request
def log_request():
    endpoint = request.endpoint or 'unknown'
    ip       = request.remote_addr
    # Block admin routes if not logged in
    allowed  = True
    if endpoint.startswith('admin_routes.') and not session.get('admin_logged_in'):
        allowed = False

    entry = {
        'time':     datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ip':       ip,
        'endpoint': endpoint,
        'status':   'Allowed' if allowed else 'Blocked'
    }
    requests_log.append(entry)
    if len(requests_log) > 100:
        requests_log.pop(0)


# Config for Uploads
app.config.from_object(Config)
app.secret_key = os.getenv("SECRET_KEY", "fallback-key")
os.makedirs(app.config['IMG_UPLOAD_FOLDER'], exist_ok=True)

# Create Tables
with app.app_context():
    create_tables()

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# Registered API Blueprints
app.register_blueprint(api_auth_routes)
app.register_blueprint(payment_routes)
app.register_blueprint(other_routes)

# Registered Web Blueprints
app.register_blueprint(admin_routes, url_prefix='/admin')

# Routes
@app.route('/status')
def status():
    return render_template('status.html', requests=requests_log)

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route("/")
def home():
    return render_template("home.html", current_year=datetime.now().year)


# App run
if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "development":
        print("Starting Flask dev server at http://0.0.0.0:8000")
        print("You can check server status at http://localhost:8000/status")
        app.run(debug=True, host="0.0.0.0", port=8000)
    else:
        print("Starting production server with Waitress at http://0.0.0.0:8000")
        print("You can check server status at http://localhost:8000/status")
        serve(app, host="0.0.0.0", port=8000)
