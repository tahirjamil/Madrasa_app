from mysql import connect_to_db

# ====== MySQL Connection ======
conn = connect_to_db()

# Helper Selectors
def gender_selector():
    gender = input("Gender (1 = Male, 2 = Female, Enter to skip): ").strip()
    return 'Male' if gender == '1' else 'Female' if gender == '2' else None

def acc_type_selector():
    acc_type = input('Account Type (1 = Admin, 2 = Student, 3 = Teacher, 4 = Staff, 5 = Guest, Enter to skip): ').strip()
    types = {'1': 'Admin', '2': 'Student', '3': 'Teacher', '4': 'Staff', '5': 'Guest'}
    return types.get(acc_type, None)

def class_finder():
    print("Select Jamāt:")
    print("1 = Moktob\n2 = Hifz\n3 = Nazara\n4 = Kitab")
    level = input("Choice: ").strip()

    if level == '1':
        number = input("Enter class number (e.g., 1, 2, 3): ").strip()
        return f'Moktob_{number}' if number else None
    elif level == '2':
        return 'Hifz'
    elif level == '3':
        return 'Nazara'
    elif level == '4':
        print("Kitab Classes:\n1 = Madani\n2 = Daora\n3 = Usulul Hadith\n4 = Ishkat\n5 = Takmil\n6 = Fazilat\n7 = Mutawassitah\n8 = Others")
        kitab_type = input("Choose: ").strip()
        options = {
            '1': 'Madani', '2': 'Daora', '3': 'Usulul Hadith',
            '4': 'Ishkat', '5': 'Takmil', '6': 'Fazilat', '7': 'Mutawassitah'
        }
        return options.get(kitab_type) or (input("Enter class name: ").strip() if kitab_type == '8' else None)
    else:
        return None

# Gather Data
def get_input(prompt):
    val = input(f"{prompt}: ").strip()
    return val if val else None

data = {
    "name_en": get_input("Enter name in English"),
    "name_bn": get_input("Enter name in Bengali"),
    "name_ar": get_input("Enter name in Arabic"),
    "date_of_birth": get_input("Enter date of birth (YYYY-MM-DD)"),
    "birth_certificate_number": get_input("Enter birth certificate number"),
    "national_id_number": get_input("Enter national ID number"),
    "blood_group": get_input("Enter blood group"),
    "gender": gender_selector(),
    "title": get_input("Enter title"),
    "source_of_information": get_input("Enter source of information"),
    "present_address": get_input("Enter present address"),
    "permanent_address": get_input("Enter permanent address"),
    "father_or_spouse": get_input("Enter father or spouse name"),
    "father_name_en": get_input("Enter father's name in English"),
    "father_name_bn": get_input("Enter father's name in Bengali"),
    "father_name_ar": get_input("Enter father's name in Arabic"),
    "mother_name_en": get_input("Enter mother's name in English"),
    "mother_name_bn": get_input("Enter mother's name in Bengali"),
    "mother_name_ar": get_input("Enter mother's name in Arabic"),
    "class": class_finder(),
    "acc_type": acc_type_selector(),
    "image_path": None  # Skipping image handling for now
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
