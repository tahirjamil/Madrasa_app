from flask import Flask
from flask_cors import CORS
from mysql import create_tables
from Users_Backend import user_routes
from Additional_Features import additional_routes
from Reset_Passwords import reset_routes
from People_DB import people_routes
from waitress import serve
import os

app = Flask(__name__)
CORS(app)
print("Flask App created")

# Config for uploads
app.config['UPLOAD_FOLDER'] = 'uploads'

# Initialize DB tables
create_tables()
print("Successfully Created all tables")

# Register Blueprints
app.register_blueprint(user_routes)
app.register_blueprint(additional_routes)
app.register_blueprint(reset_routes)
app.register_blueprint(people_routes)
print("Blueprints Registered")

# Home route showing server status
@app.route("/")
def home():
    return """
    <html>
        <head>
            <title>Server Status</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    color: #333;
                    text-align: center;
                    padding: 50px;
                }
                .status {
                    font-size: 24px;
                    color: green;
                    margin-top: 20px;
                }
                code {
                    background-color: #eee;
                    padding: 2px 6px;
                    border-radius: 4px;
                }
            </style>
        </head>
        <body>
            <h1>🚀 Server is Running</h1>
            <div class="status">All systems operational</div>
            <p>Visit <code>/register</code>, <code>/login</code>, or other endpoints as needed.</p>
        </body>
    </html>
    """

if __name__ == "__main__":
    if os.environ.get("FLASK_ENV") == "development":
        print("Starting Flask dev server at http://0.0.0.0:8000")
        app.run(debug=True, host="0.0.0.0", port=8000)
    else:
        print("Starting production server with Waitress at http://0.0.0.0:8000")
        serve(app, host="0.0.0.0", port=8000)
