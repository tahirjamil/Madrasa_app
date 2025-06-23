from flask import Flask, render_template, current_app
from flask_cors import CORS
from database import create_tables
from waitress import serve
import os
from config import Config

# API Routes
from routes.api.auth import api_auth_routes
from routes.api.payments import payment_routes
from routes.api.additionals import other_routes

# Web Routes
from routes.admin_routes import admin_routes

app = Flask(__name__)
CORS(app)


# Config for Uploads
app.config.from_object(Config)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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

# Home route showing server status
@app.route("/")
def home():
    return render_template('Server_Status.html')

if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "development":
        print("Starting Flask dev server at http://0.0.0.0:8000")
        print("You can check server status at http://localhost:8000")
        app.run(debug=True, host="0.0.0.0", port=8000)
    else:
        print("Starting production server with Waitress at http://0.0.0.0:8000")
        print("You can check server status at http://localhost:8000")
        serve(app, host="0.0.0.0", port=8000)
