from flask import Flask
from flask_cors import CORS
from mysql import connect_to_db, create_tables
from register import register_blueprint
from verification import verification_blueprint
from waitress import serve

# Initialize app and DB connection
app = Flask(__name__)
CORS(app)
conn = connect_to_db()
create_tables()

# Attach routes (via Blueprints)
app.register_blueprint(register_blueprint)
app.register_blueprint(verification_blueprint)

# Run with Waitress
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)
