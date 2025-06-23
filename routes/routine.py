from flask import Blueprint, request, jsonify
from mysql import connect_to_db

#-----------MySQL Connection-------------
conn = connect_to_db()

routine_routes = Blueprint('routine_route', __name__)

@routine_routes.route("/routine", methods=["POST"])
def get_routine():
    if conn is None:
        return jsonify({"message": "Database connection failed."}), 500

    data = request.get_json()
    lastfetched = data.get("lastfetched")

    try:
        with conn.cursor() as cursor:
            if lastfetched:
                cursor.execute("SELECT * FROM routine WHERE updated_at > %s", (lastfetched,))
            else:
                cursor.execute("SELECT * FROM routine")
            result = cursor.fetchall()
            return jsonify(result), 200
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
