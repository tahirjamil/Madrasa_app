from flask import Blueprint, request, jsonify, current_app, send_from_directory
import pymysql
import os
import pymysql.cursors
from PIL import Image
from werkzeug.utils import secure_filename
from database import connect_to_db
from logger import log_event
from config import Config

# ========== Config ==========
IMG_UPLOAD_FOLDER = os.path.join(Config.BASE_UPLOAD_FOLDER, 'people_img')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

other_routes = Blueprint('other_routes', __name__)

os.makedirs(IMG_UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@other_routes.route('/uploads/people_img/<filename>')
def uploaded_file(filename):
    filename = secure_filename(filename)  # ✅ sanitize again during fetch
    upload_folder = os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'people_img')
    file_path = os.path.join(upload_folder, filename)

    if not os.path.isfile(file_path):
        return jsonify({"message": "File not found"}), 404

    if not filename.rsplit('.', 1)[-1].lower() in {'png', 'jpg', 'jpeg', 'webp'}:
        return jsonify({"message": "File type not allowed"}), 403

    return send_from_directory(upload_folder, filename)

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

@other_routes.route('/add_people', methods=['POST'])
def add_person():
    BASE_URL = current_app.config['BASE_URL']
    
    data = request.form
    image = request.files.get('image')

    fullname = data.get('fullname')
    phone = data.get('phone')
    acc_type = data.get('acc_type')

    if not fullname or not phone or not acc_type:
        log_event("add_people_missing", phone, "Missing fields")
        return jsonify({"message": "fullname, phone and acc_type are required"}), 400

    id = get_id(phone, fullname)

    if not id:
        return jsonify({"message": "ID not found"}), 404

    fields = {
        "id": id,
        "acc_type": acc_type
    }

    # Handle image upload
    if image and image.filename:
        if allowed_file(image.filename):
            filename_base = f"{id}_{os.path.splitext(secure_filename(image.filename))[0]}"
            filename = filename_base + ".webp"  # save as .webp
            upload_folder = current_app.config.get('UPLOAD_FOLDER', IMG_UPLOAD_FOLDER)
            image_path = os.path.join(upload_folder, filename)
        
            try:
                img = Image.open(image.stream)
                img.verify()
                image.stream.seek(0)
                img = Image.open(image.stream)
                img.save(image_path, "WEBP")

                
            except Exception as e:
                return jsonify({"message": f"Failed to save image: {str(e)}"}), 500
            
            fields["image_path"] = BASE_URL + 'uploads/people_img/' + filename
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
        log_event("add_people_failed", phone, str(e))
        return jsonify({"message": f"Database error: {str(e)}"}), 500


@other_routes.route('/members', methods=['POST'])
def get_info():
    conn = connect_to_db()

    data = request.get_json()
    lastfetched = data.get('lastfetched')

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if lastfetched:
                cursor.execute("""
                    SELECT name_en, name_bn, name_ar, permanent_address, phone, image_path
                    FROM people WHERE updated_at > %s
                """, (lastfetched,))
            else:
                cursor.execute("""
                    SELECT name_en, name_bn, name_ar, permanent_address, phone, image_path
                    FROM people
                """)
            members = cursor.fetchall()
        return jsonify(members), 200
    except Exception as e:
        log_event("get_members_failed", "NULL", str(e))
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    finally:
        conn.close()


@other_routes.route("/routine", methods=["POST"])
def get_routine():
    conn = connect_to_db()
    
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
        log_event("get_routine_failed", "NULL", str(e))
        return jsonify({"message": f"Database error: {str(e)}"}), 500
