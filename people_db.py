from flask import Flask, request, jsonify
from flask_cors import CORS
import pymysql
from pymysql.cursors import DictCursor

conn = pymysql.connect(
    host='localhost',
    user='tahir',
    password='tahir',
    database='madrashadb',
    cursorclass=pymysql.cursors.DictCursor
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
    
    acc_type ENUM('Admin', 'Student', 'Teacher', 'Staff', 'Guest'),
    );
    """)

app = Flask(__name__)
CORS(app)

def get_id(phone, fullname):
    cursor.execute("SELECT id FROM users WHERE phone = %s AND fullname = %s", (phone, fullname))
    result = cursor.fetchone()
    return result['id'] if result else None

@app.route('/people', methods=['GET'])
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
    national_id = data.get('national_id')
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

    if acc_type == 'Student':
        cursor.execute("""
                       INSERT INTO people (id, 
                       name_en, name_bn, name_ar, 
                       date_of_birth, birth_certificate_number, blood_group, gender, source_of_information, 
                       present_address, permanent_address, 
                       father_name_en, father_name_bn, father_name_ar,
                       mother_name_en, mother_name_bn, mother_name_ar, 
                       class_, acc_type) values 
                       (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (id, 
                             name_en, name_bn, name_ar, 
                             date_of_birth,
                             birth_certificate_number, blood_group, gender, source_of_information, 
                             present_address, permanent_address, 
                             father_name_en, father_name_bn,
                             father_name_ar, mother_name_en, 
                             mother_name_bn, mother_name_ar, 
                             class_, acc_type))
        
    elif acc_type == 'Teacher' or acc_type == 'Admin':
        cursor.execute("""
                       INSERT INTO people (id, 
                       name_en, name_bn, name_ar, 
                       date_of_birth, national_id, blood_group, gender, title,
                       present_address, permanent_address, 
                       father_name_en, father_name_bn, father_name_ar,
                       mother_name_en, mother_name_bn, mother_name_ar, 
                       class_, acc_type) values 
                       (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (id, 
                             name_en, name_bn, name_ar, 
                             date_of_birth, national_id, blood_group, gender, title,
                             present_address, permanent_address, 
                             father_name_en, father_name_bn, father_name_ar,
                             mother_name_en, mother_name_bn, mother_name_ar, 
                             class_, acc_type))
        
    elif acc_type == 'Staff':
        cursor.execute("""
                       INSERT INTO people (id, 
                       name_en, name_bn, name_ar, 
                       date_of_birth, birth_certificate_number, national_id, blood_group, gender, title,
                       present_address, permanent_address, 
                       father_name_en, father_name_bn, father_name_ar,
                       mother_name_en, mother_name_bn, mother_name_ar, 
                       class_, acc_type) values 
                       (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (id, 
                             name_en, name_bn, name_ar, 
                             date_of_birth, national_id, blood_group, gender, title, 
                             present_address, permanent_address, 
                             father_name_en, father_name_bn, father_name_ar,
                             mother_name_en, mother_name_bn, mother_name_ar, 
                             class_, acc_type))
        
        
    elif acc_type == 'Guest':
        cursor.execute("""
                       INSERT INTO people (id, 
                       fullname, father_or_spouse, acc_type,

                       source_of_information,
                       present_address,
                       date_of_birth, blood_group, gender) values 
                       (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       """, (id, fullname, father_or_spouse, acc_type,
                             
                             source_of_information,
                             present_address,
                             date_of_birth, blood_group, gender))
    
    else:
        return jsonify({"message": "Invalid acc_type"}), 400