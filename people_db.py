from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

conn = pymysql.connect(
    host='localhost',
    user='tahir',
    password='tahir',
    database='madrashadb',
    cursorclass=DictCursor
)

cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS people (
    id INT PRIMARY KEY,
    name VARCHAR(255),
    name_en VARCHAR(255),
    name_bn VARCHAR(255),
    name_ar VARCHAR(255),
    date_of_birth DATE,
    birth_certificate_number VARCHAR(100),
    national_id_number VARCHAR(100),
    blood_group VARCHAR(20),
    gender ENUM('Male', 'Female', 'Other'),
    title_primary VARCHAR(255),
    title_secondary VARCHAR(255),
    age INT,
    source_of_information VARCHAR(255),
    present_address TEXT,
    permanent_address TEXT,
    father_or_spouse VARCHAR(255),
    father_name_en VARCHAR(255),
    father_name_bn VARCHAR(255),
    father_name_ar VARCHAR(255),
    mother_name_en VARCHAR(255),
    mother_name_bn VARCHAR(255),
    mother_name_ar VARCHAR(255),
    class VARCHAR(100),
    image_path TEXT,
    acc_type ENUM('Admin', 'Student', 'Teacher', 'Staff', 'Guest')
);
""")

app = Flask(__name__)
CORS(app)

def get_id(phone, fullname):
    cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
    result = cursor.fetchone()
    return result['id'] if result else None

@app.route('/people', methods=['POST'])
def add_person():
    data = request.get_json()
    fullname = data.get('fullname')
    phone = data.get('phone')
    id = get_id(phone, fullname)

    name_en = data.get('name_en')
    name_bn = data.get('name_bn')
    name_ar = data.get('name_ar')
    date_of_birth = data.get('date_of_birth')
    birth_certificate_number = data.get('birth_certificate_number')
    national_id = data.get('national_id')  # note this needs to map to national_id_number
    blood_group = data.get('blood_group')
    gender = data.get('gender')
    title = data.get('title')
    source_of_information = data.get('source_of_information')
    present_address = data.get('present_address')
    permanent_address = data.get('permanent_address')
    father_or_spouse = data.get('father_or_spouse')
    father_name_en = data.get('father_name_en')
    father_name_bn = data.get('father_name_bn')
    father_name_ar = data.get('father_name_ar')
    mother_name_en = data.get('mother_name_en')
    mother_name_bn = data.get('mother_name_bn')
    mother_name_ar = data.get('mother_name_ar')
    class_ = data.get('class')
    acc_type = data.get('acc_type')

    if not id:
        return jsonify({"message": "ID not found"}), 404

    if acc_type == 'Student':
        required_fields = [name_en, name_bn, name_ar, date_of_birth,
                           birth_certificate_number, blood_group, gender, source_of_information,
                           present_address, permanent_address,
                           father_name_en, father_name_bn, father_name_ar,
                           mother_name_en, mother_name_bn, mother_name_ar, class_]
        if not all(required_fields):
            return jsonify({"message": "All fields required for Student"}), 400

        cursor.execute("""
            INSERT INTO people (id, name_en, name_bn, name_ar, date_of_birth, 
            birth_certificate_number, blood_group, gender, source_of_information, 
            present_address, permanent_address, 
            father_name_en, father_name_bn, father_name_ar,
            mother_name_en, mother_name_bn, mother_name_ar, 
            class, acc_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id, name_en, name_bn, name_ar, date_of_birth,
              birth_certificate_number, blood_group, gender, source_of_information,
              present_address, permanent_address,
              father_name_en, father_name_bn, father_name_ar,
              mother_name_en, mother_name_bn, mother_name_ar,
              class_, acc_type))

    elif acc_type in ['Teacher', 'Admin']:
        required_fields = [name_en, name_bn, name_ar, date_of_birth,
                           national_id, blood_group, gender, title,
                           present_address, permanent_address,
                           father_name_en, father_name_bn, father_name_ar,
                           mother_name_en, mother_name_bn, mother_name_ar, class_]
        if not all(required_fields):
            return jsonify({"message": "All fields required for Teacher or Admin"}), 400

        cursor.execute("""
            INSERT INTO people (id, name_en, name_bn, name_ar, date_of_birth, 
            national_id_number, blood_group, gender, title_primary,
            present_address, permanent_address, 
            father_name_en, father_name_bn, father_name_ar,
            mother_name_en, mother_name_bn, mother_name_ar, 
            class, acc_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id, name_en, name_bn, name_ar, date_of_birth,
              national_id, blood_group, gender, title,
              present_address, permanent_address,
              father_name_en, father_name_bn, father_name_ar,
              mother_name_en, mother_name_bn, mother_name_ar,
              class_, acc_type))

    elif acc_type == 'Staff':
        required_fields = [name_en, name_bn, name_ar, date_of_birth,
                           national_id, blood_group, gender, title,
                           present_address, permanent_address,
                           father_name_en, father_name_bn, father_name_ar,
                           mother_name_en, mother_name_bn, mother_name_ar, class_]
        if not all(required_fields):
            return jsonify({"message": "All fields required for Staff"}), 400

        cursor.execute("""
            INSERT INTO people (id, name_en, name_bn, name_ar, date_of_birth,
            national_id_number, blood_group, gender, title_primary,
            present_address, permanent_address,
            father_name_en, father_name_bn, father_name_ar,
            mother_name_en, mother_name_bn, mother_name_ar,
            class, acc_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id, name_en, name_bn, name_ar, date_of_birth,
              national_id, blood_group, gender, title,
              present_address, permanent_address,
              father_name_en, father_name_bn, father_name_ar,
              mother_name_en, mother_name_bn, mother_name_ar,
              class_, acc_type))

    elif acc_type == 'Guest':
        if not father_or_spouse:
            return jsonify({"message": "Father or Spouse required"}), 400

        # Required
        columns = ['id', 'father_or_spouse', 'acc_type']
        values = [id, father_or_spouse, acc_type]

        # Optional
        optional_fields = {
            'source_of_information': source_of_information,
            'present_address': present_address,
            'date_of_birth': date_of_birth,
            'blood_group': blood_group,
            'gender': gender
        }

        for field, value in optional_fields.items():
            if value:
                columns.append(field)
                values.append(value)

        sql = f"INSERT INTO people ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(values))})"
        cursor.execute(sql, values)

    else:
        return jsonify({"message": "Invalid Account type"}), 400

    conn.commit()
    return jsonify({"message": "Person added successfully"}), 201

if __name__ == '__main__':
    app.run(debug=True)
