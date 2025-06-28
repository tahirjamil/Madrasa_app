import pymysql.cursors
from helpers import format_phone_number
import pymysql
from database import connect_to_db

conn = connect_to_db()

print("Choose Where To Create\n 1 = users, 2 = payment, 3 = transactions")
choice = int(input("Enter Your Preferred Choice: ").strip())
if choice == 1:
    fullname = input("Enter your Fullname").strip()
    phone = input("Enter your phone: ").strip()
    password = input("Enter your password: ").strip()
    formatted_phone = format_phone_number()

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("INSERT INTO users (fullname, phone, password) values (%s, %s, %s)", (fullname, formatted_phone, password))
            print(f"user {fullname} added")
    except Exception as e:
        print(f"Database Error {e}")
    finally:
        conn.close()

if choice == 2:
    id_num = int(input("Enter your ID").strip())
    print("1 = True, 0 = False")
    food = int(input("Eat Food? : ").strip())
    special_food = int(input("Eat Special Food? : ").strip())
    reduce_fee = int(input("Reduce fee? : ").strip())
    months = int(input("Enter Months").strip())

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("INSERT INTO users (id, food, special_food, reduce_fee, due_months) values (%s, %s, %s)", (fullname, formatted_phone, password))
            print(f"user {fullname} added")
    except Exception as e:
        print(f"Database Error {e}")
    finally:
        conn.close()




