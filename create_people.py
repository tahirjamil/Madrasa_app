import pymysql
import pymysql.cursors

conn = pymysql.connect(
        host='localhost',
        user='tahir',
        password='tahir',
        db='madrasadb',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False)

# Helper Selectors
def gender_selector():
    gender = input("Gender (1 = Male, 2 = Female, Enter to skip): ").strip()
    return 'Male' if gender == '1' else 'Female' if gender == '2' else None

def acc_type_selector():
    acc_type = input('Account Type (1 = Admin, 2 = Student, 3 = Teacher, 4 = Staff, 5 = Donors, 6 = Badri_member, 7 = Other, Enter to skip): ').strip()
    types = {'1': 'admins', '2': 'students', '3': 'teachers', '4': 'staffs', '5': 'donors', '6': 'badri_members', '7': 'others'}
    return types.get(acc_type, None)

# Gather Data
def get_input(prompt):
    val = input(f"{prompt}: ").strip()
    return val if val else None

data = {
    "name_en": get_input("Enter name in English"),
    "name_bn": get_input("Enter name in Bengali"),
    "name_ar": get_input("Enter name in Arabic"),
    "member_id": get_input("Enter member_id"),
    "student_id": get_input("Enter student_id"),
    "phone": get_input("Enter name in Phone"),
    "date_of_birth": get_input("Enter date of birth (YYYY-MM-DD)"),
    "national_id": get_input("Enter national ID number"),
    "blood_group": get_input("Enter blood group"),
    "degree": get_input("Enter degree"),
    "gender": gender_selector(),
    "title1": get_input("Enter title1"),
    "source": get_input("Enter source of information"),
    "present_address": get_input("Enter present address"),
    "address_bn": get_input("Enter present address in bd"),
    "address_ar": get_input("Enter present address in ar"),
    "permanent_address": get_input("Enter permanent address"),
    "father_or_spouse": get_input("Enter father or spouse name"),
    "mail": get_input("Enter mail"),
    "father_en": get_input("Enter father's name in English"),
    "father_bn": get_input("Enter father's name in Bengali"),
    "father_ar": get_input("Enter father's name in Arabic"),
    "mother_en": get_input("Enter mother's name in English"),
    "mother_bn": get_input("Enter mother's name in Bengali"),
    "mother_ar": get_input("Enter mother's name in Arabic"),
    "acc_type": acc_type_selector(),
    "image_path": get_input("Enter Image Path")
}

# Filter out None fields
filtered_data = {k: v for k, v in data.items() if v is not None}

# Insert into DB
def insert_person(data):
    with conn.cursor() as cursor:
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        sql = f"INSERT INTO people ({columns}) VALUES ({placeholders})"
        cursor.execute(sql, list(data.values()))
        conn.commit()
        print("Data inserted successfully!")

try:
    insert_person(filtered_data)
except Exception as e:
    print("Error inserting person:", e)
finally:
    conn.close()
