from flask import Flask, render_template
from flask_cors import CORS
from mysql import create_tables
from waitress import serve
import os

# Routes
from routes.users import user_routes
from routes.others import additional_routes
from routes.pass_reset import reset_routes
from db_people import people_routes
from routes.routine import routine_routes
from admin.admin_route import admin_routes

app = Flask(__name__)
CORS(app)

# Config for uploads
app.config['UPLOAD_FOLDER'] = os.path.join('uploads', 'people_img')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize DB tables
create_tables()

# Registered Blueprints
app.register_blueprint(user_routes)
app.register_blueprint(additional_routes)
app.register_blueprint(reset_routes)
app.register_blueprint(people_routes)
app.register_blueprint(routine_routes)
app.register_blueprint(admin_routes)

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
