from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
import os
from werkzeug.utils import secure_filename
from mysql import connect_to_db, create_tables

# ========== Config ==========
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
CORS(app)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BASE_URL = "http://localhost:5000/"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return app.send_static_file(os.path.join('uploads', filename))

# ====== MySQL Connection ======
conn = connect_to_db()
create_tables()

# ========== Helper Functions ==========
def get_id(phone, fullname):
    with conn.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
        result = cursor.fetchone()
        return result['id'] if result else None

def insert_person(fields: dict):
    with conn.cursor() as cursor:
        columns = ', '.join(fields.keys())
        placeholders = ', '.join(['%s'] * len(fields))
        sql = f"INSERT INTO people ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(fields.values()))
        conn.commit()

# ========== Route ==========
@app.route('/people', methods=['POST'])
def add_person():
    data = request.form
    image = request.files.get('image')

    fullname = data.get('fullname')
    phone = data.get('phone')
    acc_type = data.get('acc_type')
    id = get_id(phone, fullname)

    if not id:
        return jsonify({"message": "ID not found"}), 404

    fields = {
        "id": id,
        "acc_type": acc_type
    }

    # ========== Image Handling ==========
    if image and allowed_file(image.filename):
        filename = secure_filename(f"{id}_{image.filename}")
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image.save(image_path)
        fields["image_path"] = BASE_URL + image_path.replace("\\", "/")
    elif image:
        return jsonify({"message": "Invalid image file format"}), 400

    def f(k): return data.get(k)

    # ========== Account Type Handling ==========
    if acc_type == 'Student':
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'birth_certificate_number', 'blood_group', 'gender',
            'source_of_information', 'present_address', 'permanent_address',
            'father_name_en', 'father_name_bn', 'father_name_ar',
            'mother_name_en', 'mother_name_bn', 'mother_name_ar',
            'class', 'phone', 'image_path'
        ]
        if not all(f(k) for k in required):
            return jsonify({"message": "All fields required for Student"}), 400
        fields.update({k: f(k) for k in required})

    elif acc_type in ['Teacher', 'Admin', 'Staff']:
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'national_id', 'blood_group', 'gender',
            'title', 'present_address', 'permanent_address',
            'father_name_en', 'father_name_bn', 'father_name_ar',
            'mother_name_en', 'mother_name_bn', 'mother_name_ar',
            'class', 'phone', 'image_path'
        ]
        if not all(f(k) for k in required):
            return jsonify({"message": f"All fields required for {acc_type}"}), 400

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
            "phone": f("phone"),
            "image_path": fields.get("image_path")
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
        if fields.get("image_path"):
            fields["image_path"] = fields.get("image_path")

    else:
        return jsonify({"message": "Invalid Account type"}), 400

    try:
        insert_person(fields)
        return jsonify({"message": f"{acc_type} profile added successfully", "id": id}), 201
    except pymysql.err.IntegrityError:
        return jsonify({"message": "User already exists with this ID"}), 409

@app.route('/members', methods=['GET'])
def get_info():
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT name_en, name_bn, name_ar, permanent_address, phone, image_path
            FROM people
        """)
        members = cursor.fetchall()
    return jsonify(members), 200

# ========== Main ==========
if __name__ == '__main__':
    app.run(debug=True)
