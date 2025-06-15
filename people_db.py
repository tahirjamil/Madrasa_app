from flask import Blueprint, request, jsonify, current_app, send_from_directory
import pymysql
import os
import pymysql.cursors
from werkzeug.utils import secure_filename
from mysql import connect_to_db

# ========== Config ==========
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

people_routes = Blueprint('people_routes', __name__)

# Make sure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BASE_URL = "http://localhost:5000/"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@people_routes.route('/uploads/<filename>')
def uploaded_file(filename):
    # Serve the uploaded files
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# ====== Helper Functions ======

def get_db_connection():
    return connect_to_db()

def get_id(phone, fullname):
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
            result = cursor.fetchone()
            return result['id'] if result else None
    finally:
        conn.close()

def insert_person(fields: dict):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['%s'] * len(fields))
            sql = f"INSERT INTO people ({columns}) VALUES ({placeholders})"
            cursor.execute(sql, list(fields.values()))
        conn.commit()
    finally:
        conn.close()

# ========== Routes ==========

@people_routes.route('/people', methods=['POST'])
def add_person():
    data = request.form
    image = request.files.get('image')

    fullname = data.get('fullname')
    phone = data.get('phone')
    acc_type = data.get('acc_type')

    if not fullname or not phone or not acc_type:
        return jsonify({"message": "fullname, phone and acc_type are required"}), 400

    id = get_id(phone, fullname)

    if not id:
        return jsonify({"message": "ID not found"}), 404

    fields = {
        "id": id,
        "acc_type": acc_type
    }

    # Handle image upload
    if image:
        if allowed_file(image.filename):
            filename = secure_filename(f"{id}_{image.filename}")
            upload_folder = current_app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
            image_path = os.path.join(upload_folder, filename)
            try:
                image.save(image_path)
            except Exception as e:
                return jsonify({"message": f"Failed to save image: {str(e)}"}), 500
            # Construct the URL relative to /uploads route
            fields["image_path"] = BASE_URL + 'uploads/' + filename
        else:
            return jsonify({"message": "Invalid image file format"}), 400

    def f(k): 
        return data.get(k)

    # Validate and fill fields based on acc_type
    if acc_type == 'Student':
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'birth_certificate_number', 'blood_group', 'gender',
            'source_of_information', 'present_address', 'permanent_address',
            'father_name_en', 'father_name_bn', 'father_name_ar',
            'mother_name_en', 'mother_name_bn', 'mother_name_ar',
            'class', 'phone'
        ]
        # Image is optional here, so not included in required
        if not all(f(k) for k in required):
            return jsonify({"message": "All required fields must be provided for Student"}), 400
        fields.update({k: f(k) for k in required})

    elif acc_type in ['Teacher', 'Admin', 'Staff']:
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'national_id', 'blood_group', 'gender',
            'title', 'present_address', 'permanent_address',
            'father_name_en', 'father_name_bn', 'father_name_ar',
            'mother_name_en', 'mother_name_bn', 'mother_name_ar',
            'class', 'phone'
        ]
        if not all(f(k) for k in required):
            return jsonify({"message": f"All required fields must be provided for {acc_type}"}), 400

        fields.update({
            "name_en": f("name_en"),
            "name_bn": f("name_bn"),
            "name_ar": f("name_ar"),
            "date_of_birth": f("date_of_birth"),
            "national_id_number": f("national_id"),
            "blood_group": f("blood_group"),
            "gender": f("gender"),
            "title_primary": f("title"),
            "present_address": f("present_address"),
            "permanent_address": f("permanent_address"),
            "father_name_en": f("father_name_en"),
            "father_name_bn": f("father_name_bn"),
            "father_name_ar": f("father_name_ar"),
            "mother_name_en": f("mother_name_en"),
            "mother_name_bn": f("mother_name_bn"),
            "mother_name_ar": f("mother_name_ar"),
            "class": f("class"),
            "phone": f("phone")
        })

    elif acc_type == 'Guest':
        if not f("name_en") or not f("phone") or not f("father_or_spouse"):
            return jsonify({"message": "Name, Phone, and Father/Spouse are required for Guest"}), 400

        fields["name_en"] = f("name_en")
        fields["phone"] = f("phone")
        fields["father_or_spouse"] = f("father_or_spouse")

        optional = [
            "source_of_information", "present_address", "date_of_birth",
            "blood_group", "gender"
        ]
        fields.update({k: f(k) for k in optional if f(k)})

    else:
        return jsonify({"message": "Invalid Account type"}), 400

    try:
        insert_person(fields)
        return jsonify({"message": f"{acc_type} profile added successfully", "id": id}), 201
    except pymysql.err.IntegrityError:
        return jsonify({"message": "User already exists with this ID"}), 409
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500


@people_routes.route('/members', methods=['GET'])
def get_info():
    conn = get_db_connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT name_en, name_bn, name_ar, permanent_address, phone, image_path
                FROM people
            """)
            members = cursor.fetchall()
        return jsonify(members), 200
    except Exception as e:
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        conn.close()
