from quart import request, jsonify, current_app, send_from_directory
from . import user_routes
import aiomysql, os
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo
from PIL import Image
from werkzeug.utils import secure_filename
from database.database_utils import get_db_connection
from config import Config
from helpers import (get_id, insert_person, format_phone_number, is_test_mode, validate_file_upload,
    encrypt_sensitive_data, hash_sensitive_data)
from quart_babel import gettext as _
from logger import log_critical, log_error

# ========== Config ==========
@user_routes.route('/static/user_profile_img/<filename>') # TODO fix in app
async def uploaded_file(filename):
    filename = secure_filename(filename)
    upload_folder = os.path.join(Config.PROFILE_IMG_UPLOAD_FOLDER)
    file_path = os.path.join(upload_folder, filename)

    if not os.path.isfile(file_path):
        return jsonify({"message": "File not found"}), 404
    return await send_from_directory(upload_folder, filename), 200

@user_routes.route('/uploads/notices/<path:filename>')
async def notices_file(filename):
    filename = secure_filename(filename)
    upload_folder = os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'notices')
    file_path = os.path.join(upload_folder, filename)

    if not os.path.isfile(file_path):
        return jsonify({"message": _("File not found")}), 404
    return await send_from_directory(upload_folder, filename), 200

@user_routes.route('/uploads/exam_results/<path:filename>')
async def exam_results_file(filename):
    filename = secure_filename(filename)
    upload_folder = os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'exam_results')
    file_path = os.path.join(upload_folder, filename)

    if not os.path.isfile(file_path):
        return jsonify({"message": "File not found"}), 404
        
    return await send_from_directory(upload_folder, filename), 200

@user_routes.route('/uploads/gallery/<gender>/<folder>/<path:filename>')
async def gallery_file(gender, folder, filename):
    folders = ['garden', 'library', 'office', 'roof_and_kitchen', 'mosque', 'studio', 'other']
    genders = ['male', 'female', 'both']
    filename = secure_filename(filename)
    if folder not in folders or gender not in genders:
        return jsonify({"message": "Invalid folder name"}), 404
    
    file_path = os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'gallery', gender, folder, filename)
    if os.path.isfile(file_path):
        return await send_from_directory(os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'gallery', gender, folder), filename), 200
    else:
        return jsonify({"message": "File not found"}), 404
    

@user_routes.route('/uploads/gallery/classes/<folder>/<path:filename>')
async def gallery_classes_file(folder, filename):
    folders = ['hifz', 'moktob', 'meshkat', 'daora', 'ulumul_hadith', 'ifta', 'madani_nesab', 'other']
    filename = secure_filename(filename)
    if folder not in folders:
        return jsonify({"message": "Invalid folder name"}), 404
    
    file_path = os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'gallery', 'classes', folder, filename)
    if os.path.isfile(file_path):
        return await send_from_directory(os.path.join(current_app.config['BASE_UPLOAD_FOLDER'], 'gallery', 'classes', folder), filename), 200
    else:
        return jsonify({"message": "File not found"}), 404

# ========== Routes ==========

@user_routes.route('/add_people', methods=['POST'])
async def add_person():

    if is_test_mode():
        return jsonify({"success": True, "message": "App in test mode", "user_id": None, "info": None}), 201
    
    conn = await get_db_connection()
    BASE_URL = current_app.config['BASE_URL']

    data = await request.form
    image = (await request.files).get('image')

    fullname = data.get('name_en')
    phone = data.get('phone')
    
    get_acc_type = data.get('acc_type', '')

    if not get_acc_type.endswith('s'):
        get_acc_type = (f"{get_acc_type}s")

    VALID_ACCOUNT_TYPES = ['admins', 'students', 'teachers', 'staffs', 'others', 'badri_members', 'donors']
    if not get_acc_type in VALID_ACCOUNT_TYPES:
        get_acc_type = 'others'

    if not fullname or not phone or not get_acc_type:
        log_error(action="add_people_missing", trace_info=phone or "unknown", trace_info_hash=hash_sensitive_data(phone or "unknown"), trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"), message="Missing fields")
        return jsonify({"message": _("fullname, phone and acc_type are required")}), 400

    fullname = fullname.strip().lower()
    formatted_phone, msg = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": msg}), 400

    person_id = get_id(formatted_phone, fullname)
    acc_type = get_acc_type.lower()

    if not person_id:
        return jsonify({"message": _("ID not found")}), 404

    fields = {
        "user_id": person_id,
        "acc_type": acc_type
    }

    # Handle image upload
    if image and image.filename:
        ok, msg = validate_file_upload(filename=image.filename, allowed_extensions=Config.ALLOWED_PROFILE_IMG_EXTENSIONS, file_size=image.content_length)
        if not ok:
            return jsonify({"message": msg}), 400

        filename_base = f"{person_id}_{os.path.splitext(secure_filename(image.filename))[0]}"
        filename = filename_base + ".webp"  # save as .webp
        upload_folder = os.path.join(Config.PROFILE_IMG_UPLOAD_FOLDER)
        image_path = os.path.join(upload_folder, filename)
        
        try:
            img = Image.open(image.stream)
            img.verify()
            image.stream.seek(0)
            img = Image.open(image.stream)
            img.save(image_path, "WEBP")

                
        except Exception as e:
            return jsonify({"message": f"Failed to save image: {str(e)}"}), 500
            
        fields["image_path"] = BASE_URL + '/uploads/profile_pics/' + filename
    else:
        return jsonify({"message": "Invalid image file format"}), 400


    def f(k): 
        return data.get(k)

    # Validate and fill fields based on acc_type
    if acc_type == 'students':
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'birth_certificate', 'blood_group', 'gender',
            'source', 'present_address', 'present_address_hash', 'present_address_encrypted', 
            'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
            'father_en', 'father_bn', 'father_ar',
            'mother_en', 'mother_bn', 'mother_ar',
            'class', 'phone', 'student_id', 'guardian_number'
        ]
    
        if not all(f(k) for k in required):
            return jsonify({"message": _("All required fields must be provided for Student")}), 400
        fields.update({k: f(k) for k in required})

        
    elif acc_type in ['teachers', 'admins']:
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'national_id', 'blood_group', 'gender',
            'title1', 'present_address', 'present_address_hash', 'present_address_encrypted',
            'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
            'father_en', 'father_bn', 'father_ar',
            'mother_en', 'mother_bn', 'mother_ar',
            'phone'
        ]
        if not all(f(k) for k in required):
            return jsonify({"message": _("All required fields must be provided for %(type)s") % {"type": acc_type}}), 400
        fields.update({k: f(k) for k in required})

        optional = ["degree"]
        fields.update({k: f(k) for k in optional if f(k)})

    elif acc_type == 'staffs':
        required = [
            'name_en', 'name_bn', 'name_ar', 'date_of_birth',
            'national_id', 'blood_group',
            'title2', 'present_address', 'present_address_hash', 'present_address_encrypted',
            'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
            'father_en', 'father_bn', 'father_ar',
            'mother_en', 'mother_bn', 'mother_ar',
            'phone'
        ]
        if not all(f(k) for k in required):
            return jsonify({"message": _("All required fields must be provided for %(type)s") % {"type": acc_type}}), 400
        fields.update({k: f(k) for k in required})

        
    else:
        if not f("name_en") or not f("phone") or not f("father_or_spouse") or not f("date_of_birth"):
            return jsonify({"message": _("Name, Phone, and Father/Spouse are required for Guest")}), 400

        fields["name_en"] = f("name_en")
        fields["phone"] = f("phone")
        fields["father_or_spouse"] = f("father_or_spouse")
        fields["date_of_birth"] = f("date_of_birth")

        optional = [
            "source", "present_address", "present_address_hash", "present_address_encrypted",
            "blood_group", "gender", "degree"
        ]
        fields.update({k: f(k) for k in optional if f(k)})

    madrasa_name = os.getenv("MADRASA_NAME")

    ENCRYPTED_FIELDS = ["national_id_encrypted", "birth_certificate_encrypted"]
    HASH_FIELDS = ["present_address_hash", "permanent_address_hash", "address_hash"]

    for ef in ENCRYPTED_FIELDS:
        if ef in fields and fields[ef]:
            fields[ef] = encrypt_sensitive_data(fields[ef])

    for hf in HASH_FIELDS:
        if hf in fields and fields[hf]:
            fields[hf] = hash_sensitive_data(fields[hf])

    try:
        async with conn.cursor() as cursor:
            await insert_person(madrasa_name, fields, acc_type, phone)
            await conn.commit()
            await cursor.execute(f"SELECT image_path from {madrasa_name}.peoples WHERE LOWER(name_en) = %s AND phone = %s", (fullname, formatted_phone))
            row = await cursor.fetchone()
            img_path = row["image_path"] if row else None
            return jsonify({
                "success": True, 
                "message": _("%(type)s profile added successfully") % {"type": acc_type}, 
                "user_id": person_id, 
                "info": img_path
                }), 201
            
    except aiomysql.IntegrityError:
        return jsonify({"message": _("User already exists with this ID")}), 409
    except Exception as e:
        log_critical(action="add_people_failed", trace_info=phone or "unknown", trace_info_hash=hash_sensitive_data(phone or "unknown"), trace_info_encrypted=encrypt_sensitive_data(phone or "unknown"), message=str(e))
        return jsonify({"message": _("Database error: %(error)s") % {"error": str(e)}}), 500

@user_routes.route('/members', methods=['POST'])
async def get_info():
    conn = await get_db_connection()
    
    data = await request.get_json()
    lastfetched = data.get('updatedSince')
    # member_id_list = data.get('member_id')
    corrected_time = lastfetched.replace("T", " ").replace("Z", "") if lastfetched else None

    madrasa_name = os.getenv("MADRASA_NAME")

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            sql = f"""SELECT tname.en_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                    taddress.en_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                    tfather.en_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,

                    p.degree, p.gender,
                    p.blood_group,
                    p.phone, p.image_path AS picUrl, p.member_id, p.acc_type AS role,
                    COALESCE(p.title1, p.title2, p.class) AS title,

                    a.main_type AS acc_type, a.teacher, a.student, a.staff, a.donor, a.badri_member, a.special_member,

                    FROM {madrasa_name}.peoples p

                    JOIN global.acc_types a ON a.user_id = p.user_id
                    
                    JOIN global.translations tname ON tname.translation_text = p.name
                    LEFT JOIN global.translations taddress ON taddress.translation_text = p.address
                    LEFT JOIN global.translations tfather ON tfather.translation_text = p.father_name
                    LEFT JOIN global.translations tmother ON tmother.translation_text = p.mother_name

                    WHERE p.member_id IS NOT NULL"""
            params = []

            if lastfetched:
                sql += " AND updated_at > %s"
                params.append(corrected_time)
                
            await cursor.execute(sql, params)
            members = await cursor.fetchall()
        return jsonify({
            "members": members,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
            }), 200
    except Exception as e:
        log_critical(action="get_members_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=str(e))
        return jsonify({"message": _("Database error: %(error)s") % {"error": str(e)}}), 500
        

@user_routes.route("/routines", methods=["POST"])
async def get_routine():
    conn = await get_db_connection()
    data = await request.get_json()
    lastfetched = data.get("updatedSince")
    corrected_time = lastfetched.replace("T", " ").replace("Z", "") if lastfetched else None

    madrasa_name = os.getenv("MADRASA_NAME")

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            sql = f"""SELECT r.gender, r.class_group, r.class_level, r.weekday, r.serial,
            tsubject.en_text AS subject_en, tsubject.bn_text AS subject_bn, tsubject.ar_text AS subject_ar, 
            tname.en_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar 
            FROM {madrasa_name}.routines r

            JOIN global.translations tsubject ON tsubject.translation_text = r.subject 
            JOIN global.translations tname ON tname.translation_text = r.name"""
            params = []
            
            if lastfetched:
                sql += " WHERE updated_at > %s"
                params.append(corrected_time)

            sql += " ORDER BY class_level"
            
            await cursor.execute(sql, params)
            result = await cursor.fetchall()

            return jsonify({
            "routines": result,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
            }), 200
    except Exception as e:
        log_critical(action="get_routine_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=str(e))
        return jsonify({"message": _("Database error: %(error)s") % {"error": str(e)}}), 500
        

@user_routes.route('/events', methods=['POST'])
async def events():
    data = await request.get_json() or {}
    lastfetched = data.get('updatedSince')
    DHAKA = ZoneInfo("Asia/Dhaka")

    madrasa_name = os.getenv("MADRASA_NAME")

    sql = f"""SELECT e.type, e.time, e.date, e.function_url,
            ttitle.en_text AS title_en, ttitle.bn_text AS title_bn, ttitle.ar_text AS title_ar
            FROM {madrasa_name}.events e
            JOIN global.translations ttitle ON ttitle.translation_text = e.title"""
    params = []

    if lastfetched:
        try:
            cutoff = datetime.fromisoformat(lastfetched.replace("Z", "+00:00"))
            sql += " WHERE created_at > %s"
            params.append(cutoff)
        except ValueError:
            log_error(action="get_events_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=f"Invalid timestamp: {lastfetched}")
            return jsonify({"error": "Invalid updatedSince format"}), 400

    sql += " ORDER BY event_id DESC"
    
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
    except Exception as e:
        log_critical(action="get_events_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=str(e))
        return jsonify({"message": f"Database error: {e}"}), 500
        
    now_dhaka = datetime.now(DHAKA)
    today     = now_dhaka.date()

    for ev in rows:
        ev_dt = ev.get("date") or ev.get("event_date")

        if isinstance(ev_dt, datetime):
            ev_dt_local = ev_dt.astimezone(DHAKA)
            ev_date     = ev_dt_local.date()
            ev["date"]  = ev_dt_local.isoformat()

        elif isinstance(ev_dt, date):
            ev_date = ev_dt
            ev["date"] = ev_dt.isoformat()

        else:
            ev_date = None

        if ev_date:
            if ev_date > today:
                ev["type"] = "upcoming"
            elif ev_date == today:
                ev["type"] = "ongoing"
            else:
                ev["type"] = "past"
        else:
            ev["status"] = "unknown"

    return jsonify({
        "events": rows,
        "lastSyncedAt": datetime.now(timezone.utc)
                             .isoformat().replace("+00:00","Z")
    }), 200

@user_routes.route('/exams', methods=['POST'])
async def get_exams():
    conn = await get_db_connection()
    data = await request.get_json()
    lastfetched = data.get("updatedSince")
    cutoff = lastfetched.replace("T", " ").replace("Z", "") if lastfetched else None

    madrasa_name = os.getenv("MADRASA_NAME")

    sql = f"""SELECT e.class, e.gender, e.start_time, e.end_time, e.date, e.weekday, e.sec_start_time, e.sec_end_time,
            tbook.en_text AS book_en, tbook.bn_text AS book_bn, tbook.ar_text AS book_ar
            FROM {madrasa_name}.exams e
            JOIN global.translations tbook ON tbook.translation_text = e.book"""
    params = []

    if lastfetched:
        try:
            sql += " WHERE created_at > %s"
            params.append(cutoff)

        except ValueError:
            log_error(action="get_exams_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=f"Invalid timestamp: {lastfetched}")
            return jsonify({"error": "Invalid updatedSince format"}), 400
    
    sql += " ORDER BY exam_id"

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            
            return jsonify({
                "exams": result,
                "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                })
        
    except Exception as e:
        log_critical(action="get_exams_failed", trace_info="unknown", trace_info_hash=hash_sensitive_data("unknown"), trace_info_encrypted=encrypt_sensitive_data("unknown"), message=str(e))
        return jsonify({"message": f"Database error: {e}"}), 500