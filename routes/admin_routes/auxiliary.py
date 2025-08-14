from . import admin_routes
from database.database_utils import connect_to_db
from utils.helpers import handle_async_errors
from quart import jsonify, session, redirect, url_for, current_app
import aiomysql
from config import config

@admin_routes.route('/logs/data')
@handle_async_errors
async def logs_data():
    try:
        conn = await connect_to_db()

        if conn is None or config.is_testing():
            return jsonify([])
    except Exception as e:
        return jsonify([])
    
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT log_id, action, phone, message, created_at FROM logs ORDER BY created_at DESC")
            logs = await cursor.fetchall()
        # Convert datetime to string
        for l in logs:
            l['created_at'] = l['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(logs)
    except Exception as e:
        return jsonify([])



@admin_routes.route('/info/data')
@handle_async_errors
async def info_data_admin():
    # require admin
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))
    
    if config.is_testing():
        return jsonify([])

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
#                     cursor.execute("SELECT * FROM peoples WHERE user_id = %s", (user_id,))
#                     member = cursor.fetchone()
#             finally:
#                 await conn.close()

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
#             upload_path = os.path.join(current_app.config['PROFILE_IMG_UPLOAD_FOLDER'], filename)
#             image.save(upload_path)
#             data['image_path'] = upload_path  # or just filename if you store relative path

#         conn = connect_to_db()
#         try:
#             with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                 cols = ','.join(data.keys())
#                 vals = ','.join(['%s']*len(data))
#                 cursor.execute(
#                   f"INSERT INTO peoples ({cols}) VALUES ({vals})",
#                   tuple(data.values())
#                 )
#                 conn.commit()
#             flash("Member added successfully","success")
#             return redirect(url_for('admin_routes.members'))
#         finally:
#             await conn.close()

#     return render_template('admin/manage_member.html',
#                            genders=genders,
#                            types=types,
#                            blood_groups=blood_groups,
#                            member=member)



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



# TODO: Disabled for view-only mode
# @admin_routes.route('/routines/add', methods=['GET', 'POST'])
# def add_routine():
#     conn = connect_to_db()
#     # 1) require login
#     if not session.get('admin_logged_in'):
#         return redirect(url_for('admin_routes.login'))

#     if request.method == 'POST':
#         # 2) grab form values
#         data = request.form.to_dict()
#         # TODO: validate & possibly look up IDs from peoples/books table
#         # e.g. if data['name_mode']=='user_id': lookup the three name fields...
#         # then insert into routines table:
#         try:
#             with conn.cursor() as cursor:
#                 cursor.execute("""
#                     INSERT INTO routines
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
#             return redirect(url_for('admin_routes.routines'))
#         except Exception as e:
#             flash(f"Error adding routine: {e}", "danger")
#         finally:
#             await conn.close()

#     # GET → show form
#     return render_template('admin/add_routine.html')



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
#     pic_path = os.path.join(GALLERY_DIR, filename)
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

