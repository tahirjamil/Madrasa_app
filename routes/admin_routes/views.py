from flask import render_template, request, flash, session, redirect, url_for, current_app
import pymysql
import pymysql.cursors
from . import admin_routes
from database import connect_to_db
import os
from datetime import datetime, date
from logger import log_event
from werkzeug.utils import secure_filename
from helpers import load_results, load_notices, save_notices, save_results, allowed_exam_file, allowed_notice_file
from config import Config
import json
import re

#  DIRS
EXAM_DIR     = Config.EXAM_DIR
NOTICES_DIR = Config.NOTICES_DIR
MADRASA_IMG_DIR = Config.MADRASA_IMG_DIR
PIC_INDEX_PATH       = os.path.join(MADRASA_IMG_DIR, 'index.json')

# RE
_FORBIDDEN_RE = re.compile(
    r'\b(?:drop|truncate|alter|rename|create\s+database|use)\b',
    re.IGNORECASE
)

# ------------- Root / Dashboard ----------------

@admin_routes.route('/', methods=['GET', 'POST'])
def admin_dashboard():
    # 1) Ensure admin is logged in
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    databases = []
    tables = {}
    selected_db = request.args.get('db', 'madrasadb')
    query_result = None
    query_error = None

    # --- Payment Transactions Section ---
    txn_limit = request.args.get('txn_limit', '100')
    txn_limit_val = 100
    if txn_limit == '200':
        txn_limit_val = 200
    elif txn_limit == 'all':
        txn_limit_val = None

    transactions = []
    student_payments = []
    student_class = request.args.get('student_class', 'all')

    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            # Load database list
            cursor.execute("SHOW DATABASES")
            databases = [row["Database"] for row in cursor.fetchall()]

            # Validate selected_db
            if selected_db not in databases:
                selected_db = databases[0] if databases else None

            # Load tables & descriptions
            if selected_db:
                cursor.execute(f"USE `{selected_db}`")
                cursor.execute("SHOW TABLES")
                table_list = [row[f'Tables_in_{selected_db}'] for row in cursor.fetchall()]
                for table in table_list:
                    cursor.execute(f"DESCRIBE `{table}`")
                    tables[table] = cursor.fetchall()

            # Handle SQL form submission
            if request.method == "POST":
                raw_sql = request.form.get('sql', '').strip()
                username = request.form.get('username', '')
                password = request.form.get('password', '')

                ADMIN_USER = os.getenv("ADMIN_USERNAME")
                ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

                # Authenticate admin credentials
                if username != ADMIN_USER or password != ADMIN_PASS:
                    flash("Unauthorized admin login.", "danger")
                # Forbid dangerous keywords (whole‑word match)
                elif _FORBIDDEN_RE.search(raw_sql):
                    flash("🚫 Dangerous queries are not allowed (DROP, ALTER, etc).", "danger")
                    log_event("forbidden_query_attempt", username, raw_sql)
                else:
                    try:
                        cursor.execute(raw_sql)
                        # If it's a SELECT or similar, fetch results
                        if cursor.description:
                            query_result = cursor.fetchall()
                        else:
                            conn.commit()
                            query_result = f"✅ Query OK. Rows affected: {cursor.rowcount}"
                        log_event("query_run", username, raw_sql)
                    except Exception as e:
                        query_error = str(e)
                        log_event("query_error", username, f"{raw_sql} | {str(e)}")

            # --- Fetch transactions ---
            txn_sql = "SELECT * FROM transactions ORDER BY date DESC"
            if txn_limit_val:
                txn_sql += f" LIMIT {txn_limit_val}"
            cursor.execute(txn_sql)
            transactions = cursor.fetchall()

            # --- Fetch all students payment info ---
            student_sql = '''
                SELECT users.fullname, users.phone, people.class, people.gender, payment.special_food, payment.reduce_fee,
                       payment.food, payment.due_months AS month, payment.id, payment.id as user_id
                FROM users
                JOIN people ON people.id = users.id
                JOIN payment ON payment.id = users.id
                WHERE people.acc_type = 'students'
            '''
            params = []
            if student_class and student_class != 'all':
                student_sql += " AND people.class = %s"
                params.append(student_class)
            student_sql += " ORDER BY people.class, users.fullname"
            cursor.execute(student_sql, params)
            student_payments = cursor.fetchall()

    except Exception as e:
        query_error = str(e)
    finally:
        conn.close()

    return render_template(
        "admin/dashboard.html",
        databases=databases,
        tables=tables,
        selected_db=selected_db,
        query_result=query_result,
        query_error=query_error,
        transactions=transactions,
        txn_limit=txn_limit,
        student_payments=student_payments,
        student_class=student_class
    )


# ------------------ Logs ---------------------


@admin_routes.route('/logs')
def view_logs():
    # Require admin login
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT log_id, action, phone, message, created_at "
                "FROM logs "
                "ORDER BY created_at DESC"
            )
            logs = cursor.fetchall()
    finally:
        conn.close()

    return render_template("admin/logs.html", logs=logs)

from flask import jsonify

@admin_routes.route('/logs/data')
def logs_data():
    conn = connect_to_db()
    with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT log_id, action, phone, message, created_at FROM logs ORDER BY created_at DESC")
        logs = cursor.fetchall()
    conn.close()
    # Convert datetime to string
    for l in logs:
        l['created_at'] = l['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    return jsonify(logs)



@admin_routes.route('/info/data')
def info_data_admin():
    # require admin
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    logs = getattr(current_app, 'request_response_log', [])[-100:]
    # serializable copy
    out = []
    for e in logs:
        out.append({
            "time":     e["time"],
            "ip":       e["ip"],
            "method":   e["method"],
            "path":     e["path"],
            "req_json": e.get("req_json"),
            "res_json": e.get("res_json")
        })
    return jsonify(out)


@admin_routes.route('/info')
def info_admin():
    # require admin
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    logs = getattr(current_app, 'request_response_log', [])[-100:]
    return render_template("admin/info.html", logs=logs)




# ------------------ Exam Results ------------------------

# TODO: Disabled for view-only mode
# @admin_routes.route('/exam_results', methods=['GET', 'POST'])
# def exam_results():
#     # auth
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     if request.method == 'POST':
#         username    = request.form.get('username')
#         password    = request.form.get('password')
#         exam_date   = request.form.get('exam_date')
#         exam_type   = request.form.get('exam_type')
#         exam_class  = request.form.get('exam_class')
#         file        = request.files.get('file')

#         ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
#         ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")

#         if username != ADMIN_USER or password != ADMIN_PASS:
#             flash("Unauthorized", "danger")
#             return redirect(url_for('admin_routes.exam_results'))

#         if file and file.filename and allowed_exam_file(file.filename):
#             filename = secure_filename(file.filename)
#             filepath = os.path.join(EXAM_DIR, filename)
#             file.save(filepath)

#             results = load_results()
#             results.append({
#                 "filename":    filename,
#                 "exam_date":   exam_date,
#                 "exam_type":   exam_type,
#                 "exam_class":  exam_class,
#                 "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#             })
#             save_results(results)

#             flash("Exam result uploaded.", "success")
#             log_event("exam_uploaded", username, filename)
#         else:
#             flash("Invalid file format.", "warning")

#         return redirect(url_for('admin_routes.exam_results'))

#     # GET: show all together
#     results = load_results()
#     return render_template("admin/exam_results.html", results=results)


# TODO: Disabled for view-only mode
# @admin_routes.route('/exam_results/delete/<filename>', methods=['POST'])
# def delete_exam_result(filename):
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     username = request.form.get('username')
#     password = request.form.get('password')
#     ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
#     ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin123")
#     if username != ADMIN_USER or password != ADMIN_PASS:
#         flash("Unauthorized", "danger")
#         return redirect(url_for('admin_routes.exam_results'))

#     filepath = os.path.join(EXAM_DIR, filename)
#     if os.path.exists(filepath):
#         os.remove(filepath)

#     results = load_results()
#     results = [r for r in results if r['filename'] != filename]
#     save_results(results)

#     flash(f"Deleted {filename}.", "info")
#     log_event("exam_deleted", username, filename)
#     return redirect(url_for('admin_routes.exam_results'))


# ------------------- Members --------------------------

@admin_routes.route('/members', methods=['GET', 'POST'])
def members():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # Fetch all people and pending verifies
            cursor.execute("SELECT * FROM people")
            people = list(cursor.fetchall())
            cursor.execute("SELECT * FROM verify_people")
            pending = cursor.fetchall()
    finally:
        conn.close()

    # Build list of distinct account types
    types = sorted({m['acc_type'] for m in people if m.get('acc_type')})
    selected_type = request.args.get('type', types[0] if types else None)
    sort_key = request.args.get('sort', 'user_id_asc')

    # Filter members by type (or all)
    if selected_type == 'all':
        members = people[:]
    else:
        members = [m for m in people if m['acc_type'] == selected_type] if selected_type else []

    # Sorting logic
    reverse = False
    if sort_key.endswith('_desc'):
        reverse = True
    if sort_key.startswith('name_en'):
        members.sort(key=lambda m: (m.get('name_en') or '').lower(), reverse=reverse)
    elif sort_key.startswith('member_id'):
        def member_id_int(m):
            try:
                return int(m.get('member_id') or 0)
            except Exception:
                return 0
        members.sort(key=member_id_int, reverse=reverse)
    else:  # default user_id
        def user_id_int(m):
            try:
                return int(m.get('user_id') or 0)
            except Exception:
                return 0
        members.sort(key=user_id_int, reverse=reverse)

    return render_template("admin/members.html",
                           types=types,
                           selected_type=selected_type,
                           members=members,
                           pending=pending,
                           sort=sort_key)


# TODO: Disabled for view-only mode
# @admin_routes.route('/member/<modify>', methods=['GET','POST'])
# def manage_member(modify):
#     pages = ['add','edit']
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     if not modify in pages:
#         return redirect(url_for('admin_routes.members'))

#     genders = ['Male','Female']
#     blood_groups = ['A+','A-','B+','B-','AB+','AB-','O+','O-']
#     types = ['admins','students','teachers','staffs','donors','badri_members','others']

#     member = None
#     if modify == 'edit':
#         user_id = request.args.get('user_id')
#         if user_id:
#             conn = connect_to_db()
#             try:
#                 with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                     cursor.execute("SELECT * FROM people WHERE user_id = %s", (user_id,))
#                     member = cursor.fetchone()
#             finally:
#                 conn.close()

#     if request.method == 'POST':
#         fields = ["name_en","name_bn","name_ar","member_id","student_id","phone",
#                   "date_of_birth","national_id","blood_group","degree","gender",
#                   "title1","source","address_en","address_bn","address_ar",
#                   "permanent_address","father_or_spouse","father_en",
#                   "father_bn","father_ar","mother_en","mother_bn","mother_ar",
#                   "acc_type"]
#         data = {f: request.form.get(f) for f in fields if request.form.get(f)}

#         # Handle image upload
#         image = request.files.get('image')
#         if image and image.filename:
#             filename = secure_filename(image.filename)
#             upload_path = os.path.join(current_app.config['IMG_UPLOAD_FOLDER'], filename)
#             image.save(upload_path)
#             data['image_path'] = upload_path  # or just filename if you store relative path

#         conn = connect_to_db()
#         try:
#             with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                 cols = ','.join(data.keys())
#                 vals = ','.join(['%s']*len(data))
#                 cursor.execute(
#                   f"INSERT INTO people ({cols}) VALUES ({vals})",
#                   tuple(data.values())
#                 )
#                 conn.commit()
#             flash("Member added successfully","success")
#             return redirect(url_for('admin_routes.members'))
#         finally:
#             conn.close()

#     return render_template('admin/manage_member.html',
#                            genders=genders,
#                            types=types,
#                            blood_groups=blood_groups,
#                            member=member)




# ------------------- Notices -----------------------

# TODO: Disabled for view-only mode
# @admin_routes.route('/notice', methods=['GET', 'POST'])
# def notice_page():
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))
#     if request.method == 'POST':
#         username = request.form.get('username')
#         password = request.form.get('password')
#         target_date = request.form.get('target_date')
#         file = request.files.get('file')

#         ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
#         ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin")

#         if username != ADMIN_USER or password != ADMIN_PASS:
#             flash("Unauthorized", "danger")
#             return redirect(url_for('admin_routes.notice_page'))

#         if file and file.filename and allowed_notice_file(file.filename):
#             filename = secure_filename(file.filename)
#             filepath = os.path.join(NOTICES_DIR, filename)
#             file.save(filepath)

#             notices = load_notices()
#             notices.append({
#                 "filename": filename,
#                 "target_date": target_date,
#                 "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#             })
#             save_notices(notices)

#             flash("Notice uploaded.", "success")
#             log_event("notice_uploaded", username, filename)
#         else:
#             flash("Invalid file format.", "warning")

#         return redirect(url_for('admin_routes.notice_page'))

#     notices = load_notices()
#     today = date.today()
#     upcoming, ongoing, past = [], [], []

#     for n in notices:
#         try:
#             n_date = datetime.strptime(n['target_date'], '%Y-%m-%d').date()
#             if n_date > today:
#                 upcoming.append(n)
#             elif n_date == today:
#                 ongoing.append(n)
#             else:
#                 past.append(n)
#         except Exception:
#             past.append(n)

#     return render_template("admin/notice.html",
#                            upcoming=upcoming,
#                            ongoing=ongoing,
#                            past=past)


# TODO: Disabled for view-only mode
# @admin_routes.route('/notice/delete/<filename>', methods=['POST'])
# def delete_notice(filename):
#     username = request.form.get('username')
#     password = request.form.get('password')

#     ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
#     ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "admin")

#     if username != ADMIN_USER or password != ADMIN_PASS:
#         flash("Unauthorized", "danger")
#         return redirect(url_for('admin_routes.notice_page'))

#     filepath = os.path.join(NOTICES_DIR, filename)
#     if os.path.exists(filepath):
#         os.remove(filepath)

#     notices = load_notices()
#     notices = [n for n in notices if n['filename'] != filename]
#     save_notices(notices)

#     flash(f"Notice '{filename}' deleted.", "info")
#     log_event("notice_deleted", username, filename)
#     return redirect(url_for('admin_routes.notice_page'))


# ------------------ Routine ----------------------

@admin_routes.route('/routine', methods=['GET'])
def routine():
    # require login
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    sort = request.args.get('sort', 'default')

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("""
                SELECT *
                  FROM routine
                 ORDER BY class_group ASC, serial ASC
            """)
            rows = cursor.fetchall()
    finally:
        conn.close()

    # group by class_group
    routines_by_class = {}
    for r in rows:
        routines_by_class.setdefault(r['class_group'], []).append(r)

    # Sorting logic
    if sort == 'class':
        routines_by_class = dict(sorted(routines_by_class.items(), key=lambda x: x[0]))
    elif sort == 'weekday':
        weekday_order = ['saturday','sunday','monday','tuesday','wednesday','thursday','friday']
        for k in routines_by_class:
            routines_by_class[k].sort(key=lambda r: weekday_order.index(r['weekday'].lower()) if r['weekday'] else 0)
    elif sort == 'serial':
        for k in routines_by_class:
            routines_by_class[k].sort(key=lambda r: int(r.get('serial', 0)))
    # else: default (serial from db order)

    return render_template(
        'admin/routine.html',
        routines_by_class=routines_by_class,
        sort=sort
    )

# TODO: Disabled for view-only mode
# @admin_routes.route('/routine/add', methods=['GET', 'POST'])
# def add_routine():
#     conn = connect_to_db()
#     # 1) require login
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     if request.method == 'POST':
#         # 2) grab form values
#         data = request.form.to_dict()
#         # TODO: validate & possibly look up IDs from people/book tables
#         # e.g. if data['name_mode']=='id': lookup the three name fields...
#         # then insert into routine table:
#         try:
#             with conn.cursor() as cursor:
#                 cursor.execute("""
#                     INSERT INTO routine
#                       (gender, class_group, class_level, weekday,
#                        subject_en, subject_bn, subject_ar,
#                        name_en,    name_bn,    name_ar,
#                        serial)
#                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
#                 """, [
#                     data['gender'],
#                     data['class_group'],
#                     data['class_level'],
#                     data['weekday'],
#                     data.get('subject_en'),
#                     data.get('subject_bn'),
#                     data.get('subject_ar'),
#                     data.get('name_en'),
#                     data.get('name_bn'),
#                     data.get('name_ar'),
#                     data['serial']
#                 ])
#                 conn.commit()
#             flash("Routine added successfully.", "success")
#             return redirect(url_for('admin_routes.routine'))
#         except Exception as e:
#             flash(f"Error adding routine: {e}", "danger")
#         finally:
#             conn.close()

#     # GET → show form
#     return render_template('admin/add_routine.html')




# -------------------- Event / Function ------------------------

# TODO: Disabled for view-only mode
# @admin_routes.route('/events', methods=['GET', 'POST'])
# def events():
#     # ─── require login ────────────────────────────────────────────
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     conn = connect_to_db()
#     events = []
#     try:
#         with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
#             # ─── handle form submission ────────────────────────────
#             if request.method == 'POST':
#                 username     = request.form.get('username', '').strip()
#                 password     = request.form.get('password', '').strip()
#                 ADMIN_USER   = os.getenv("ADMIN_USERNAME")
#                 ADMIN_PASS   = os.getenv("ADMIN_PASSWORD")

#                 if username != ADMIN_USER or password != ADMIN_PASS:
#                     flash("❌ Invalid admin credentials.", "danger")
#                 else:
#                     title        = request.form.get('title', '').strip()
#                     evt_type     = request.form.get('type')
#                     date_str     = request.form.get('date')       # YYYY-MM-DD
#                     time_str     = request.form.get('time')       # HH:MM
#                     function_url = request.form.get('function_url') or None

#                     # Combine into a full timestamp string
#                     # MySQL will parse "YYYY-MM-DD HH:MM"
#                     datetime_str = f"{date_str} {time_str}"

#                     cursor.execute("""
#                         INSERT INTO events
#                           (type, title, time, date, function_url)
#                         VALUES (%s, %s, %s, %s, %s)
#                     """, (evt_type, title, datetime_str, date_str, function_url))
#                     conn.commit()
#                     flash("✅ Event added successfully.", "success")

#             # ─── fetch all events ────────────────────────────────────
#             cursor.execute("""
#                 SELECT event_id, type, title, date, time, function_url
#                   FROM events
#                  ORDER BY date  DESC,
#                           time  DESC
#             """)
#             events = cursor.fetchall()

#     except Exception as e:
#         flash(f"⚠️ Database error: {e}", "danger")

#     finally:
#         conn.close()

#     return render_template("admin/events.html", events=events)




# ------------------- Madrasa Pictures ------------------------

# Ensure the folder & index exist
os.makedirs(MADRASA_IMG_DIR, exist_ok=True)
if not os.path.exists(PIC_INDEX_PATH):
    with open(PIC_INDEX_PATH, 'w') as f:
        json.dump([], f)


# TODO: Disabled for view-only mode
# @admin_routes.route('/madrasa_pictures', methods=['GET', 'POST'])
# def madrasa_pictures():
#     # 1) Require admin
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     # 2) Handle upload
#     if request.method == 'POST':
#         username     = request.form.get('username', '')
#         password     = request.form.get('password', '')
#         class_name   = request.form.get('class_name', '').strip()
#         floor_number = request.form.get('floor_number', '').strip()
#         serial       = request.form.get('serial', '').strip()
#         file         = request.files.get('file')

#         ADMIN_USER = os.getenv('ADMIN_USERNAME')
#         ADMIN_PASS = os.getenv('ADMIN_PASSWORD')

#         if username != ADMIN_USER or password != ADMIN_PASS:
#             flash('Invalid admin credentials', 'danger')
#             return redirect(url_for('admin_routes.madrasa_pictures'))

#         if not file or not file.filename:
#             flash('No file selected', 'danger')
#             return redirect(url_for('admin_routes.madrasa_pictures'))

#         filename = secure_filename(file.filename)
#         save_path = os.path.join(MADRASA_IMG_DIR, filename)
#         file.save(save_path)

#         # 3) Update index.json
#         with open(PIC_INDEX_PATH, 'r+') as idx:
#             data = json.load(idx)
#             data.append({
#                 'filename'    : filename,
#                 'class_name'  : class_name,
#                 'floor_number': floor_number,
#                 'serial'      : serial,
#                 'uploaded_at' : datetime.now().strftime('%Y-%m-%d %H:%M:%S')
#             })
#             idx.seek(0)
#             json.dump(data, idx, indent=2)
#             idx.truncate()

#         flash('Picture uploaded!', 'success')
#         return redirect(url_for('admin_routes.madrasa_pictures'))

#     # 4) On GET: load current list
#     with open(PIC_INDEX_PATH) as idx:
#         pictures = json.load(idx)

#     return render_template('admin/madrasa_pictures.html', pictures=pictures)


# TODO: Disabled for view-only mode
# @admin_routes.route('/madrasa_pictures/delete/<filename>', methods=['POST'])
# def delete_picture(filename):
#     # 1) Require admin
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     username = request.form.get('username', '')
#     password = request.form.get('password', '')

#     ADMIN_USER = os.getenv('ADMIN_USERNAME')
#     ADMIN_PASS = os.getenv('ADMIN_PASSWORD')

#     if username != ADMIN_USER or password != ADMIN_PASS:
#         flash('Invalid admin credentials', 'danger')
#         return redirect(url_for('admin_routes.madrasa_pictures'))

#     # 2) Remove file
#     pic_path = os.path.join(MADRASA_IMG_DIR, filename)
#     if os.path.exists(pic_path):
#         os.remove(pic_path)

#     # 3) Update index.json to drop that entry
#     with open(PIC_INDEX_PATH, 'r+') as idx:
#         data = json.load(idx)
#         data = [p for p in data if p['filename'] != filename]
#         idx.seek(0)
#         json.dump(data, idx, indent=2)
#         idx.truncate()

#     flash('Picture deleted.', 'success')
#     return redirect(url_for('admin_routes.madrasa_pictures'))



# ---------------------- Exam -----------------------------

@admin_routes.route('/admin/events/exams', methods=['GET', 'POST'])
def exams():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # Fetch all exams
    cursor.execute("SELECT * FROM exam ORDER BY date DESC, start_time ASC")
    exams = cursor.fetchall()

    conn.close()
    return render_template('admin/exams.html', exams=exams)

@admin_routes.route('/admin/add_exam', methods=['POST'])
def add_exam():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    # ✅ Re-check admin credentials
    username = request.form.get('username')
    password = request.form.get('password')

    if username != current_app.config['ADMIN_USERNAME'] or password != current_app.config['ADMIN_PASSWORD']:
        return "Invalid admin credentials", 403

    # ✅ Get form fields
    cls = request.form.get('class')
    gender = request.form.get('gender')
    weekday = request.form.get('weekday')
    date = request.form.get('date')

    # ✅ Combine date + time
    def combine(date_str, time_str):
        return f"{date_str} {time_str}:00" if date_str and time_str else None

    start_time = combine(date, request.form.get('start_time'))
    end_time = combine(date, request.form.get('end_time'))
    sec_start_time = combine(date, request.form.get('sec_start_time'))
    sec_end_time = combine(date, request.form.get('sec_end_time'))

    # ✅ Book fields
    book_mode = request.form.get('book_mode')

    conn = connect_to_db()
    cursor = conn.cursor()

    if book_mode == 'id':
        book_id = request.form.get('book_id')
        cursor.execute("SELECT book_en, book_bn, book_ar FROM book WHERE book_id = %s", (book_id,))
        book = cursor.fetchone()
        if not book:
            conn.close()
            return "Book ID not found", 400
        book_en, book_bn, book_ar = book
    else:
        book_en = request.form.get('book_en')
        book_bn = request.form.get('book_bn')
        book_ar = request.form.get('book_ar')

    # ✅ Insert exam
    cursor.execute("""
        INSERT INTO exam (
            class, gender, weekday, date,
            start_time, end_time, sec_start_time, sec_end_time,
            book_en, book_bn, book_ar
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        cls, gender, weekday, date,
        start_time, end_time, sec_start_time, sec_end_time,
        book_en, book_bn, book_ar
    ))

    conn.commit()
    conn.close()

    return redirect(url_for('admin_routes.exams'))

@admin_routes.route('/members/delete_pending/<int:verify_people_id>', methods=['POST'])
def delete_pending_member(verify_people_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("DELETE FROM verify_people WHERE id = %s", (verify_people_id,))
            conn.commit()
            flash("Pending verification deleted.", "info")
            log_event("pending_verification_deleted", session.get('admin_username', 'admin'), f"ID {verify_people_id}")
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting pending verification: {e}", "danger")
        log_event("delete_pending_error", session.get('admin_username', 'admin'), str(e))
    finally:
        conn.close()

    return redirect(url_for('admin_routes.members'))

# TODO: Disabled for view-only mode
# @admin_routes.route('/payment/<modify>', methods=['GET', 'POST'])
# def modify_payment(modify):
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))
#     pages = ["edit", "add"]
#     if modify not in pages:
#         return redirect(url_for('admin_routes.admin_dashboard'))

#     mode = modify
#     user_id = request.args.get('user_id')
#     payment = None
#     if user_id:
#         conn = connect_to_db()
#         try:
#             with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                 cursor.execute("SELECT * FROM payment WHERE id = %s", (user_id,))
#                 payment = cursor.fetchone()
#         finally:
#             conn.close()

#     if request.method == 'POST':
#         id_val = request.form.get('id')
#         food = 1 if request.form.get('food') else 0
#         special_food = 1 if request.form.get('special_food') else 0
#         reduce_fee = request.form.get('reduce_fee') or 0
#         due_months = request.form.get('due_months') or 0
#         conn = connect_to_db()
#         try:
#             with conn.cursor() as cursor:
#                 if mode == 'edit':
#                     cursor.execute(
#                         "UPDATE payment SET food=%s, special_food=%s, reduce_fee=%s, due_months=%s WHERE id=%s",
#                         (food, special_food, reduce_fee, due_months, id_val)
#                     )
#                     conn.commit()
#                     flash("Payment info updated.", "success")
#                 else:  # add
#                     cursor.execute(
#                         "INSERT INTO payment (id, food, special_food, reduce_fee, due_months) VALUES (%s, %s, %s, %s, %s)",
#                         (id_val, food, special_food, reduce_fee, due_months)
#                     )
#                     conn.commit()
#                     flash("Payment info added.", "success")
#             return redirect(url_for('admin_routes.admin_dashboard'))
#         finally:
#             conn.close()

#     return render_template('admin/payment_form.html', payment=payment, mode=mode)

@admin_routes.route('/interactions', methods=['GET'])
def interactions():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    sort = request.args.get('sort', 'default')
    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM interactions")
            rows = list(cursor.fetchall())
    finally:
        conn.close()

    # Sorting logic
    if sort == 'device_brand':
        rows.sort(key=lambda r: (r.get('device_brand') or '').lower())
    elif sort == 'ip_address':
        rows.sort(key=lambda r: (r.get('ip_address') or '').lower())
    elif sort == 'open_times':
        rows.sort(key=lambda r: int(r.get('open_times', 0)), reverse=True)
    # else: default order

    return render_template('admin/interactions.html', interactions=rows, sort=sort)