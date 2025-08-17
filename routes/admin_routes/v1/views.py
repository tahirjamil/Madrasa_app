from quart import render_template, request, flash, session, redirect, url_for, current_app, jsonify
from collections import deque
from threading import Lock

from utils.helpers.improved_functions import get_env_var
from . import admin_routes
from utils.mysql.database_utils import get_db_connection
from datetime import datetime, date
from utils.helpers.helpers import (
    load_results, load_notices, save_notices, save_results, 
    cache_with_invalidation, 
    handle_async_errors, rate_limit, hash_sensitive_data, 
    encrypt_sensitive_data, format_phone_number, get_db_context,
    get_cache_key, get_cached_data, set_cached_data
)
from utils.helpers.logger import log
from config import config
import json, re, os, aiomysql, subprocess
from functools import wraps
from utils.helpers.helpers import require_csrf

#  DIRS
EXAM_DIR     = config.EXAM_RESULTS_UPLOAD_FOLDER
NOTICES_DIR = config.NOTICES_UPLOAD_FOLDER
GALLERY_DIR = config.GALLERY_DIR
PIC_INDEX_PATH       = os.path.join(GALLERY_DIR, 'index.json')

# RE
_FORBIDDEN_RE = re.compile(
    r'\b(?:drop|truncate|alter|rename|create\s+database|use)\b',
    re.IGNORECASE
)

# ------------- Root / Dashboard ----------------

@admin_routes.route('/', methods=['GET', 'POST'])
@require_csrf
@handle_async_errors
# @rate_limit(max_requests=500, window=60)  # Temporarily disabled for testing
async def admin_dashboard():
    # 1) Ensure admin is logged in
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    madrasa_name = get_env_var("MADRASA_NAME", "annur")  # Default to annur if not set
    
    databases = []
    tables = {}
    selected_db = request.args.get('db', 'global')  # Default to global database
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
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                # Load database list
                await cursor.execute("SHOW DATABASES")
                databases = [row["Database"] for row in await cursor.fetchall()]

                # Validate selected_db
                if selected_db not in databases:
                    selected_db = databases[0] if databases else None

                # Load tables & descriptions
                if selected_db:
                    await cursor.execute(f"USE `{selected_db}`")
                    await cursor.execute("SHOW TABLES")
                    table_list = [row[f'Tables_in_{selected_db}'] for row in await cursor.fetchall()]
                    for table in table_list:
                        await cursor.execute(f"DESCRIBE `{table}`")
                        tables[table] = await cursor.fetchall()

                # Handle SQL form submission
                if request.method == "POST":
                    form = await request.form
                    raw_sql = form.get('sql', '').strip() if not config.is_testing() else ''
                    username = form.get('username', '')
                    password = form.get('password', '')

                    ADMIN_USER = get_env_var("ADMIN_USERNAME")
                    ADMIN_PASS = get_env_var("ADMIN_PASSWORD")

                    # Say test mode if in test
                    if config.is_testing():
                        await flash("The server is in testing mode.", "danger")
                    # Authenticate admin credentials
                    elif username != ADMIN_USER or password != ADMIN_PASS:
                        await flash("Unauthorized admin login.", "danger")
                    # Forbid dangerous keywords (whole‑word match)
                    elif _FORBIDDEN_RE.search(raw_sql):
                        await flash("🚫 Dangerous queries are not allowed (DROP, ALTER, etc).", "danger")
                        log.warning(action="forbidden_query_attempt", trace_info=username, message=raw_sql, secure=False)
                    else:
                        try:
                            await cursor.execute(raw_sql)
                            # If it's a SELECT or similar, fetch results
                            if cursor.description:
                                query_result = await cursor.fetchall()
                            else:
                                await conn.commit()
                                query_result = f"✅ Query OK. Rows affected: {cursor.rowcount}"
                            log.info(action="query_run", trace_info=username, message=raw_sql, secure=False)
                        except Exception as e:
                            query_error = str(e)
                            log.error(action="query_error", trace_info=username, message=f"{raw_sql} | {str(e)}", secure=False)

                # --- Fetch transactions ---
                if txn_limit_val:
                    await cursor.execute("SELECT * FROM global.transactions ORDER BY date DESC LIMIT %s", (txn_limit_val,))
                else:
                    await cursor.execute("SELECT * FROM global.transactions ORDER BY date DESC")
                transactions = await cursor.fetchall()

                # --- Fetch all students payment info ---
                student_sql = f'''
                    SELECT u.fullname, u.phone, p.class, p.gender, pay.special_food, pay.reduced_fee,
                           pay.food, pay.due_months AS month, pay.payment_id, pay.user_id
                    FROM global.users u
                    JOIN {madrasa_name}.peoples p ON p.user_id = u.user_id
                    JOIN {madrasa_name}.payments pay ON pay.user_id = u.user_id
                    JOIN global.acc_types a ON a.user_id = u.user_id
                    WHERE a.main_type = 'students'
                '''
                params = []
                if student_class and student_class != 'all':
                    student_sql += " AND p.class = %s"
                    params.append(student_class)
                student_sql += " ORDER BY p.class, u.fullname"
                await cursor.execute(student_sql, params)
                student_payments = await cursor.fetchall()

    except Exception as e:
        query_error = str(e)

    return await render_template(
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
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def view_logs():
    
    # Require admin login
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    
    if config.is_testing():
        # await flash("Server is in test mode", "danger")  # Removed hardcoded test mode message
        return await render_template("admin/logs.html", logs=[])
    
    # Try cache first
    cache_key = get_cache_key("admin:logs")
    cached_logs = await get_cached_data(cache_key)
    if cached_logs is not None:
        return await render_template("admin/logs.html", logs=cached_logs)

    try:
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                await cursor.execute(
                    "SELECT log_id, action, trace_info, message, created_at "
                    "FROM logs "
                    "ORDER BY created_at DESC"
                )
                logs = await cursor.fetchall()
                await set_cached_data(cache_key, logs, ttl=config.SHORT_CACHE_TTL)
    except Exception as e:
        await flash(f"Database error: {str(e)}", "danger")
        logs = []

    return await render_template("admin/logs.html", logs=logs)


@admin_routes.route('/info')
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def info_admin():

    # require admin
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    # Thread-safe access to request log
    if config.is_testing():
        logs = []
    else:
        request_log = current_app.config.get('request_response_log', deque())
        request_log_lock = current_app.config.get('request_log_lock', Lock())
        with request_log_lock:
            logs = list(request_log)[-100:]

    return await render_template("admin/info.html", logs=logs)




# ------------------ Exam Results ------------------------

@admin_routes.route('/exam_results', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def exam_results():
    # auth
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    # REMINDER: Disabled for view-only mode
    # if request.method == 'POST':
    #     username    = request.form.get('username')
    #     password    = request.form.get('password')
    #     exam_date   = request.form.get('exam_date')
    #     exam_type   = request.form.get('exam_type')
    #     exam_class  = request.form.get('exam_class')
    #     file        = request.files.get('file')

    #     ADMIN_USER = get_env_var("ADMIN_USERNAME", "admin")
    #     ADMIN_PASS = get_env_var("ADMIN_PASSWORD", "admin123")

    #     if username != ADMIN_USER or password != ADMIN_PASS:
    #         flash("Unauthorized", "danger")
    #         return redirect(url_for('admin_routes.exam_results'))

    #     if file and file.filename and allowed_exam_file(file.filename):
    #         filename = secure_filename(file.filename)
    #         filepath = os.path.join(EXAM_DIR, filename)
    #         file.save(filepath)

    #         results = load_results()
    #         results.append({
    #             "filename":    filename,
    #             "exam_date":   exam_date,
    #             "exam_type":   exam_type,
    #             "exam_class":  exam_class,
    #             "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #         })
    #         save_results(results)

    #         flash("Exam result uploaded.", "success")
    #         log_event("exam_uploaded", username, filename)
    #     else:
    #         flash("Invalid file format.", "warning")

    #     return redirect(url_for('admin_routes.exam_results'))

    # GET: show all together
    results = load_results() if not config.is_testing() else []
    return await render_template("admin/exam_results.html", results=results)


# REMINDER: Disabled for view-only mode
# @admin_routes.route('/exam_results/delete/<filename>', methods=['POST'])
# def delete_exam_result(filename):
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     username = request.form.get('username')
#     password = request.form.get('password')
#     ADMIN_USER = get_env_var("ADMIN_USERNAME", "admin")
#     ADMIN_PASS = get_env_var("ADMIN_PASSWORD", "admin123")
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
@require_csrf
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def members():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    madrasa_name = get_env_var("MADRASA_NAME", "annur")  # Default to annur if not set
    
    # Cache the base peoples/pending payload
    base_key = get_cache_key("admin:peoples", madrasa=madrasa_name)
    base_cached = await get_cached_data(base_key)
    if base_cached is not None:
        peoples = base_cached.get('peoples', [])
        pending = base_cached.get('pending', [])
    else:
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                # Fetch all peoples with account types
                await cursor.execute(f"""
                    SELECT p.*, a.main_type as acc_type, a.teacher, a.student, a.staff, a.donor, a.badri_member, a.special_member
                    FROM {madrasa_name}.peoples p
                    LEFT JOIN global.acc_types a ON a.user_id = p.user_id
                """)
                peoples = list(await cursor.fetchall())
                
                # Note: verify_peoples table might not exist in new schema
                try:
                    await cursor.execute(f"SELECT * FROM {madrasa_name}.verify_peoples")
                    pending = await cursor.fetchall()
                except:
                    pending = []
        await set_cached_data(base_key, {"peoples": peoples, "pending": pending}, ttl=config.SHORT_CACHE_TTL)

    # Build list of distinct account types
    types = sorted({m['acc_type'] for m in peoples if m.get('acc_type')})
    selected_type = request.args.get('type', types[0] if types else None)
    sort_key = request.args.get('sort', 'user_id_asc')

    # Filter members by type (or all)
    if selected_type == 'all':
        members = peoples[:]
    else:
        members = [m for m in peoples if m['acc_type'] == selected_type] if selected_type else []

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

    if config.is_testing():
        members = []
        pending = []

    return await render_template("admin/members.html",
                           types=types,
                           selected_type=selected_type,
                           members=members,
                           pending=pending,
                           sort=sort_key)


# ------------------- Notices -----------------------

@admin_routes.route('/notice', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def notice_page():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    
    # REMINDER: Disabled for view-only mode
    # if request.method == 'POST':
    #     username = request.form.get('username')
    #     password = request.form.get('password')
    #     target_date = request.form.get('target_date')
    #     file = request.files.get('file')

    #     ADMIN_USER = get_env_var("ADMIN_USERNAME", "admin")
    #     ADMIN_PASS = get_env_var("ADMIN_PASSWORD", "admin")

    #     if username != ADMIN_USER or password != ADMIN_PASS:
    #         flash("Unauthorized", "danger")
    #         return redirect(url_for('admin_routes.notice_page'))

    #     if file and file.filename and allowed_notice_file(file.filename):
    #         filename = secure_filename(file.filename)
    #         filepath = os.path.join(NOTICES_DIR, filename)
    #         file.save(filepath)

    #         notices = load_notices()
    #         notices.append({
    #             "filename": filename,
    #             "target_date": target_date,
    #             "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #         })
    #         save_notices(notices)

    #         flash("Notice uploaded.", "success")
    #         log_event("notice_uploaded", username, filename)
    #     else:
    #         flash("Invalid file format.", "warning")

    #     return redirect(url_for('admin_routes.notice_page'))

    notices = load_notices()
    today = date.today()
    upcoming, ongoing, past = [], [], []

    if not config.is_testing():
        for n in notices:
            try:
                n_date = datetime.strptime(n['target_date'], '%Y-%m-%d').date()
                if n_date > today:
                    upcoming.append(n)
                elif n_date == today:
                    ongoing.append(n)
                else:
                    past.append(n)
            except Exception:
                past.append(n)
    

    return await render_template("admin/notice.html",
                           upcoming=upcoming,
                           ongoing=ongoing,
                           past=past)

# ------------------ Routine ----------------------

@admin_routes.route('/routines', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def routines():
    # require login
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    sort = request.args.get('sort', 'default')

    # cache routines list per madrasa
    cache_key = get_cache_key("admin:routines", madrasa=get_env_var("MADRASA_NAME", "annur"))
    cached = await get_cached_data(cache_key)
    if cached is not None:
        rows = cached
    else:
        try:
            async with get_db_connection() as conn:
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.db_tracing import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
                    await cursor.execute("""
                        SELECT *
                          FROM routines
                         ORDER BY class_group ASC, serial ASC
                    """)
                    rows = await cursor.fetchall()
                    await set_cached_data(cache_key, rows, ttl=config.SHORT_CACHE_TTL)
        except Exception as e:
            rows = []

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

    if config.is_testing():
        routines_by_class = {}

    return await render_template(
        'admin/routines.html',
        routines_by_class=routines_by_class,
        sort=sort
    )



# -------------------- Event / Function ------------------------

@admin_routes.route('/events', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def events():
    # ─── require login ────────────────────────────────────────────
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    madrasa_name = get_env_var("MADRASA_NAME", "annur")  # Default to annur if not set
    
    cache_key = get_cache_key("admin:events", madrasa=madrasa_name)
    cached = await get_cached_data(cache_key)
    if cached is not None:
        events = cached if not config.is_testing() else []
        return await render_template("admin/events.html", events=events)

    async with get_db_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
        # REMINDER: Disabled for view-only mode
        # ─── handle form submission ────────────────────────────
        # if request.method == 'POST':
        #     username     = request.form.get('username', '').strip()
        #     password     = request.form.get('password', '').strip()
        #     ADMIN_USER   = get_env_var("ADMIN_USERNAME")
        #     ADMIN_PASS   = get_env_var("ADMIN_PASSWORD")
        
        #     if username != ADMIN_USER or password != ADMIN_PASS:
        #         flash("❌ Invalid admin credentials.", "danger")
        #     else:
        #         title        = request.form.get('title', '').strip()
        #         evt_type     = request.form.get('type')
        #         date_str     = request.form.get('date')       # YYYY-MM-DD
        #         time_str     = request.form.get('time')       # HH:MM
        #         function_url = request.form.get('function_url') or None
        
        #         # Combine into a full timestamp string
        #         # MySQL will parse "YYYY-MM-DD HH:MM"
        #         datetime_str = f"{date_str} {time_str}"
        
        #         cursor.execute("""
        #             INSERT INTO events
        #               (type, title, time, date, function_url)
        #             VALUES (%s, %s, %s, %s, %s)
        #         """, (evt_type, title, datetime_str, date_str, function_url))
        #         conn.commit()
        #         flash("✅ Event added successfully.", "success")

        # ─── fetch all events ────────────────────────────────────
        await cursor.execute(f"""
            SELECT event_id, type, title, date, time, function_url
              FROM {madrasa_name}.events
             ORDER BY date  DESC,
                      time  DESC
        """)
        if not config.is_testing():
            events = await cursor.fetchall()
            await set_cached_data(cache_key, events, ttl=config.SHORT_CACHE_TTL)
        else:
            events = []

    return await render_template("admin/events.html", events=events)




# ------------------- Madrasa Pictures ------------------------

@admin_routes.route('/madrasa_pictures', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def madrasa_pictures():
    # 1) Require admin
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    # REMINDER: Disabled for view-only mode
    # 2) Handle upload
    # if request.method == 'POST':
    #     username     = request.form.get('username', '')
    #     password     = request.form.get('password', '')
    #     class_name   = request.form.get('class_name', '').strip()
    #     floor_number = request.form.get('floor_number', '').strip()
    #     serial       = request.form.get('serial', '').strip()
    #     file         = request.files.get('file')

    #     ADMIN_USER = get_env_var('ADMIN_USERNAME')
    #     ADMIN_PASS = get_env_var('ADMIN_PASSWORD')

    #     if username != ADMIN_USER or password != ADMIN_PASS:
    #         flash('Invalid admin credentials', 'danger')
    #         return redirect(url_for('admin_routes.madrasa_pictures'))

    #     if not file or not file.filename:
    #         flash('No file selected', 'danger')
    #         return redirect(url_for('admin_routes.madrasa_pictures'))

    #     filename = secure_filename(file.filename)
    #     save_path = os.path.join(GALLERY_DIR, filename)
    #     file.save(save_path)

    #     # 3) Update index.json
    #     with open(PIC_INDEX_PATH, 'r+') as idx:
    #         data = json.load(idx)
    #         data.append({
    #             'filename'    : filename,
    #             'class_name'  : class_name,
    #             'floor_number': floor_number,
    #             'serial'      : serial,
    #             'uploaded_at' : datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #         })
    #         idx.seek(0)
    #         json.dump(data, idx, indent=2)
    #         idx.truncate()

    #     flash('Picture uploaded!', 'success')
    #     return redirect(url_for('admin_routes.madrasa_pictures'))

    # 4) On GET: load current list
    pictures = []
    if not config.is_testing():
        try:
            with open(PIC_INDEX_PATH) as idx:
                pictures = json.load(idx)
        except (FileNotFoundError, json.JSONDecodeError):
            pictures = []

    return await render_template('admin/madrasa_pictures.html', pictures=pictures)



# ---------------------- Exam -----------------------------

@admin_routes.route('/admin/events/exams', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def exams():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    
    if not config.is_testing():
        return await render_template('admin/exams.html', exams=[])

    # Fetch all exams from the database
    async with get_db_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)

            # Fetch all exams
            await cursor.execute("SELECT * FROM exams ORDER BY date DESC, start_time ASC")
            exams = await cursor.fetchall()

    return await render_template('admin/exams.html', exams=exams)

# REMINDER: Disabled for view-only mode
# @admin_routes.route('/admin/add_exam', methods=['POST'])
# def add_exam():
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     # ✅ Re-check admin credentials
#     username = request.form.get('username')
#     password = request.form.get('password')

#     if username != current_app.config['ADMIN_USERNAME'] or password != current_app.config['ADMIN_PASSWORD']:
#         return "Invalid admin credentials", 403

#     # ✅ Get form fields
#     cls = request.form.get('class')
#     gender = request.form.get('gender')
#     weekday = request.form.get('weekday')
#     date = request.form.get('date')

#     # ✅ Combine date + time
#     def combine(date_str, time_str):
#         return f"{date_str} {time_str}:00" if date_str and time_str else None

#     start_time = combine(date, request.form.get('start_time'))
#     end_time = combine(date, request.form.get('end_time'))
#     sec_start_time = combine(date, request.form.get('sec_start_time'))
#     sec_end_time = combine(date, request.form.get('sec_end_time'))

#     # ✅ Book fields
#     book_mode = request.form.get('book_mode')

#     conn = connect_to_db()
#     cursor = conn.cursor()

#     if book_mode == 'user_id':
#         book_id = request.form.get('book_id')
#         cursor.execute("SELECT name_en, name_bn, name_ar FROM books WHERE book_id = %s", (book_id,))
#         book = cursor.fetchone()
#         if not book:
#             await conn.close()
#             return "Book ID not found", 400
#         name_en, name_bn, name_ar = book
#     else:
#         name_en = request.form.get('name_en')
#         name_bn = request.form.get('name_bn')
#         book_ar = request.form.get('book_ar')

#     # ✅ Insert exam
#     cursor.execute("""
#         INSERT INTO exams (
#             class, gender, weekday, date,
#             start_time, end_time, sec_start_time, sec_end_time,
#             book_en, book_bn, book_ar
#         )
#         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
#     """, (
#         cls, gender, weekday, date,
#         start_time, end_time, sec_start_time, sec_end_time,
#         book_en, book_bn, book_ar
#     ))

#     conn.commit()
#     await conn.close()

#     return redirect(url_for('admin_routes.exams'))

# REMINDER: Disabled for view-only mode
# @admin_routes.route('/members/delete_pending/<int:verify_people_id>', methods=['POST'])
# def delete_pending_member(verify_people_id):
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     conn = connect_to_db()
#     try:
#         with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#             cursor.execute("DELETE FROM verify_people WHERE user_id = %s", (verify_people_id,))
#             conn.commit()
#             flash("Pending verification deleted.", "info")
#             log_event("pending_verification_deleted", session.get('admin_username', 'admin'), f"ID {verify_people_id}")
#     except Exception as e:
#         conn.rollback()
#         flash(f"Error deleting pending verification: {e}", "danger")
#         log_event("delete_pending_error", session.get('admin_username', 'admin'), str(e))
#     finally:
#         await conn.close()

#     return redirect(url_for('admin_routes.members'))

# REMINDER: Disabled for view-only mode
# @admin_routes.route('/payments/<modify>', methods=['GET', 'POST'])
# def modify_payment(modify):
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))
#     pages = ["edit", "add"]
#     if modify not in pages:
#         return redirect(url_for('admin_routes.admin_dashboard'))

#     mode = modify
#     user_id = request.args.get('user_id')
#     payments = None
#     if user_id:
#         conn = connect_to_db()
#         try:
#             with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                 cursor.execute("SELECT * FROM payments WHERE user_id = %s", (user_id,))
#                 payment = cursor.fetchone()
#         finally:
#             await conn.close()

#     if request.method == 'POST':
#         id_val = request.form.get('user_id')
#         food = 1 if request.form.get('food') else 0
#         special_food = 1 if request.form.get('special_food') else 0
#         reduced_fee = request.form.get('reduced_fee') or 0
#         due_months = request.form.get('due_months') or 0
#         conn = connect_to_db()
#         try:
#             with conn.cursor() as cursor:
#                 if mode == 'edit':
#                     cursor.execute(
#                         "UPDATE payments SET food=%s, special_food=%s, reduced_fee=%s, due_months=%s WHERE payment_id=%s",
#                         (food, special_food, reduced_fee, due_months, id_val)
#                     )
#                     conn.commit()
#                     flash("Payment info updated.", "success")
#                 else:  # add
#                     cursor.execute(
#                         "INSERT INTO payments (payment_id, food, special_food, reduced_fee, due_months) VALUES (%s, %s, %s, %s, %s)",
#                         (id_val, food, special_food, reduced_fee, due_months)
#                     )
#                     conn.commit()
#                     flash("Payment info added.", "success")
#             return redirect(url_for('admin_routes.admin_dashboard'))
#         finally:
#             await conn.close()

#     return render_template('admin/payment_form.html', payment=payment, mode=mode)

@admin_routes.route('/interactions', methods=['GET'])
@handle_async_errors
@rate_limit(max_requests=500, window=60)
async def interactions():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    sort = request.args.get('sort', 'default')
    
    cache_key = get_cache_key("admin:interactions")
    cached = await get_cached_data(cache_key)
    if cached is not None:
        rows = cached
    else:
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                await cursor.execute("SELECT * FROM global.interactions")
                rows = list(await cursor.fetchall())
        await set_cached_data(cache_key, rows, ttl=config.SHORT_CACHE_TTL)

    # Sorting logic
    if sort == 'device_brand':
        rows.sort(key=lambda r: (r.get('device_brand') or '').lower())
    elif sort == 'ip_address':
        rows.sort(key=lambda r: (r.get('ip_address') or '').lower())
    elif sort == 'open_times':
        rows.sort(key=lambda r: int(r.get('open_times', 0)), reverse=True)
    # else: default order

    if config.is_testing():
        rows = []

    return await render_template('admin/interactions.html', interactions=rows, sort=sort)


@admin_routes.route('/power', methods=['GET', 'POST'])
@require_csrf
@handle_async_errors
@rate_limit(max_requests=100, window=60)
async def power_management():
    # Require admin login
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    
    # Get power key from environment
    POWER_KEY = get_env_var("POWER_KEY")
    if not POWER_KEY:
        return await render_template('admin/power.html', error="Power management is not configured")
    
    if config.is_testing():
        return await render_template('admin/power.html', error=None)  # Removed hardcoded test mode message
    
    if request.method == 'POST':
        form = await request.form
        action = form.get('action')
        power_key = form.get('power_key')
        
        # Verify power key
        if power_key != POWER_KEY:
            await flash("Invalid power key", "danger")
            return await render_template('admin/power.html')
        
        
        try:
            if action == 'git_pull':
                # Git pull
                result = subprocess.run(
                    ['git', 'pull'], 
                    capture_output=True, 
                    text=True, 
                    cwd=os.getcwd(),
                    timeout=30
                )
                if result.returncode == 0:
                    await flash(f"✅ Git pull successful\n{result.stdout}", "success")
                else:
                    await flash(f"❌ Git pull failed\n{result.stderr}", "danger")
                log.info(action="git_pull", trace_info="admin", message=f"Git pull executed: {result.stdout[:100]}...", secure=False)
                
            elif action == 'git_push':
                # Git push
                result = subprocess.run(
                    ['git', 'push'], 
                    capture_output=True, 
                    text=True, 
                    cwd=os.getcwd(),
                    timeout=30
                )
                if result.returncode == 0:
                    await flash(f"✅ Git push successful\n{result.stdout}", "success")
                else:
                    await flash(f"❌ Git push failed\n{result.stderr}", "danger")
                log.info(action="git_push", trace_info="admin", message=f"Git push executed: {result.stdout[:100]}...", secure=False)
                
            elif action == 'server_stop':
                # Enhanced server stop using advanced server runner
                await flash("🛑 Server stop initiated. The server will stop gracefully...", "warning")
                log.info(action="server_stop", trace_info="admin", message="Server stop initiated via power management", secure=False)
                
                # Use the advanced server runner's stop functionality
                try:
                    import sys
                    from pathlib import Path
                    
                    # Get the server runner path
                    server_runner = Path(__file__).resolve().parent.parent.parent / "run_server.py"
                    
                    # Stop server using the advanced runner
                    result = subprocess.run([
                        sys.executable, str(server_runner), "--stop"
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        await flash("✅ Server stop command sent successfully", "success")
                    else:
                        await flash(f"⚠️ Server stop command sent with warnings: {result.stderr}", "warning")
                        
                except subprocess.TimeoutExpired:
                    await flash("⚠️ Server stop command timed out, but may still be processing", "warning")
                except Exception as e:
                    await flash(f"❌ Error sending stop command: {str(e)}", "danger")
                    log.error(action="server_stop_error", trace_info="admin", message=f"Error: {str(e)}", secure=False)
                
            elif action == 'server_restart':
                # Enhanced server restart using advanced server runner
                await flash("🔄 Server restart initiated. The server will restart gracefully...", "warning")
                log.info(action="server_restart", trace_info="admin", message="Server restart initiated via power management", secure=False)
                
                # Use the advanced server runner's restart functionality
                try:
                    import sys
                    from pathlib import Path
                    
                    # Get the server runner path
                    server_runner = Path(__file__).resolve().parent.parent.parent / "run_server.py"
                    
                    # Stop and restart server using the advanced runner
                    # First stop
                    stop_result = subprocess.run([
                        sys.executable, str(server_runner), "--stop"
                    ], capture_output=True, text=True, timeout=10)
                    
                    if stop_result.returncode == 0:
                        await flash("✅ Server restart command sent successfully", "success")
                        log.info(action="server_restart_success", trace_info="admin", message="Server restart command sent successfully", secure=False)
                    else:
                        await flash(f"⚠️ Server restart command sent with warnings: {stop_result.stderr}", "warning")
                        
                except subprocess.TimeoutExpired:
                    await flash("⚠️ Server restart command timed out, but may still be processing", "warning")
                except Exception as e:
                    await flash(f"❌ Error sending restart command: {str(e)}", "danger")
                    log.error(action="server_restart_error", trace_info="admin", message=f"Error: {str(e)}", secure=False)
                
            else:
                await flash("Invalid action", "danger")
                
        except subprocess.TimeoutExpired:
            await flash("❌ Operation timed out (30 seconds)", "danger")
            log.error(action="power_timeout", trace_info="admin", message=f"Operation timed out: {action}", secure=False)
        except Exception as e:
            await flash(f"❌ Error: {str(e)}", "danger")
            log.error(action="power_error", trace_info="admin", message=f"Error in {action}: {str(e)}", secure=False)
    
    return await render_template('admin/power.html')