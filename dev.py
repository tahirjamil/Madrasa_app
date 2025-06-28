import pymysql.cursors
from helpers import format_phone_number
from database import connect_to_db

def _type_select():
    print("1 = donations, 2 = fees")
    num = int(input("Enter Type: "))
    return "donations" if num == 1 else "fees"

print("Choose Where To Create\n 1 = users, 2 = payment, 3 = transactions")
choice = int(input("Enter Your Preferred Choice: ").strip())

if choice == 1:
    fullname = input("Enter your Fullname: ").strip()
    phone = input("Enter your phone: ").strip()
    password = input("Enter your password: ").strip()
    formatted_phone = format_phone_number(phone)

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO users (fullname, phone, password) VALUES (%s, %s, %s)",
                (fullname, formatted_phone, password)
            )
        conn.commit()
        print(f"User {fullname} added")
    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

elif choice == 2:
    id_num = int(input("Enter your ID: ").strip())
    food = int(input("Eat Food? (1 = Yes, 0 = No): ").strip())
    special_food = int(input("Eat Special Food? (1 = Yes, 0 = No): ").strip())
    reduce_fee = int(input("Reduce fee? (1 = Yes, 0 = No): ").strip())
    months = int(input("Enter number of months: ").strip())

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO payments (id, food, special_food, reduce_fee, due_months) VALUES (%s, %s, %s, %s, %s)",
                (id_num, food, special_food, reduce_fee, months)
            )
        conn.commit()
        print(f"Payment info for user ID {id_num} added")
    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

elif choice == 3:
    id_num = int(input("Enter your ID: ").strip())
    amount = int(input("Enter Amount: ").strip())
    date = input("Enter Date (YYYY-MM-DD): ").strip()
    _type = _type_select()
    months = int(input("Enter number of months: ").strip())

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "INSERT INTO transactions (id, type, amount, date, month) VALUES (%s, %s, %s, %s, %s)",
                (id_num, _type, amount, date, months)
            )
        conn.commit()
        print(f"Transaction for user ID {id_num} added")
    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        conn.close()

else:
    print("Invalid choice.")
