import os
import re
from datetime import datetime, date, timezone
from typing import Any, Dict, Tuple, List
from zoneinfo import ZoneInfo

import aiomysql
from PIL import Image
from quart import (
    current_app, jsonify, request, send_from_directory, 
    Response, Request
)
from werkzeug.utils import secure_filename

# Local imports
from . import api
from database.database_utils import get_db_connection
from config import config
from utils.helpers import (
    format_phone_number, get_client_info, get_id, insert_person, invalidate_cache_pattern, get_cache_key,
    rate_limit, cache_with_invalidation, secure_data, security_manager, set_cached_data, get_cached_data,
    encrypt_sensitive_data, hash_sensitive_data, handle_async_errors,
    metrics_collector, validate_file_upload, validate_fullname, validate_request_origin,
)
from quart_babel import gettext as _
from utils.logger import log

# ─── Configuration and Constants ───────────────────────────────────────────────

ERROR_MESSAGES = {
        'file_not_found': _("File not found"),
        'invalid_folder': _("Invalid folder name"),
        'invalid_gender': _("Invalid gender parameter"),
        'file_too_large': _("File size exceeds maximum allowed size"),
        'invalid_file_type': _("Invalid file type"),
        'missing_required_fields': _("Missing required fields"),
        'invalid_phone': _("Invalid phone number format"),
        'invalid_name': _("Invalid name format"),
        'rate_limit_exceeded': _("Rate limit exceeded. Please try again later."),
        'maintenance_mode': _("Application is currently in maintenance mode"),
        'unauthorized': _("Unauthorized access"),
        'internal_error': _("An internal error occurred"),
        'validation_error': _("Validation error"),
        'database_error': _("Database operation failed")
    }

# ─── Data Management Routes ─────────────────────────────────────────────────

@api.route('/add_people', methods=['POST'])
@rate_limit(max_requests=config.STRICT_RATE_LIMIT, window=3600)
@handle_async_errors
async def add_person() -> Tuple[Response, int]:
    """Add a new person to the system with comprehensive validation and security """
    # Test mode handling
    if config.is_testing():
        return jsonify({
            "success": True, 
            "message": "App in test mode", 
            "user_id": None, 
            "info": None
        }), 201
    
    try:
        # Get form data
        data = await request.form
        files = await request.files
        image = files.get('image')
        madrasa_name = data.get("madrasa_name") or os.getenv("MADRASA_NAME")
        
        # Validate required fields using enhanced validation
        required_fields = ['name_en', 'phone', 'acc_type']
        missing_fields = [f for f in required_fields if not data.get(f)]
        if missing_fields:
            log.warning(action="add_people_missing_fields", trace_info=data.get("ip_address", ""), message=f"Missing required fields: {missing_fields}", secure=False)
            return jsonify({
                "message": _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}
            }), 400
        
        # Extract and validate basic fields with sanitization
        fullname = data.get('name_en')
        phone = data.get('phone')
        acc_type = data.get('acc_type')
        
        # Validate fullname
        is_valid_name, name_error = validate_fullname(fullname)
        if not is_valid_name:
            return jsonify({"message": name_error}), 400
        
        # Validate and format phone number
        formatted_phone, phone_error = format_phone_number(phone)
        if not formatted_phone:
            return jsonify({"message": phone_error}), 400
        
        # Normalize account type
        if not acc_type.endswith('s'):
            acc_type = f"{acc_type}s"
        
        VALID_ACCOUNT_TYPES = [
            'admins', 'students', 'teachers', 'staffs', 
            'others', 'badri_members', 'donors'
        ]
        if acc_type not in VALID_ACCOUNT_TYPES:
            acc_type = 'others'
        
        # Get user ID
        person_id = await get_id(formatted_phone, fullname.lower())
        if not person_id:
            log.error(action="add_people_id_not_found", trace_info=formatted_phone, message="User ID not found", secure=True)
            return jsonify({"message": _("ID not found")}), 404
        
        # Initialize fields dictionary
        fields: Dict[str, Any] = {"user_id": person_id}
        
        # Set account type boolean fields
        fields.update({
            "teacher": data.get('teacher', '0') == '1' or acc_type == 'teachers',
            "student": data.get('student', '0') == '1' or acc_type == 'students',
            "staff": data.get('staff', '0') == '1' or acc_type == 'staffs',
            "donor": data.get('donor', '0') == '1' or acc_type == 'donors',
            "badri_member": data.get('badri_member', '0') == '1' or acc_type == 'badri_members',
            "special_member": data.get('special_member', '0') == '1'
        })
        
        # Handle image upload with enhanced security
        if image and image.filename:
            # Validate file upload
            is_valid_file, file_error = validate_file_upload(
                file=image,
                allowed_extensions=list(config.ALLOWED_PROFILE_IMG_EXTENSIONS),
            )
            
            if not is_valid_file:
                return jsonify({"message": file_error}), 400
            
            # Generate secure filename
            filename_base = f"{person_id}_{os.path.splitext(secure_filename(image.filename))[0]}"
            filename = filename_base + ".webp"
            upload_folder = config.PROFILE_IMG_UPLOAD_FOLDER
            image_path = os.path.join(upload_folder, filename)
            
            try:
                # Process and save image
                img = Image.open(image.stream)
                img.verify()  # Verify image integrity
                image.stream.seek(0)
                img = Image.open(image.stream)
                
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Save as WebP for better compression
                img.save(image_path, "WEBP", quality=85)
                
                # Set image path
                BASE_URL = current_app.config['BASE_URL']
                fields["image_path"] = f"{BASE_URL}/uploads/profile_pics/{filename}"
                
            except Exception as e:
                log.critical(action="image_processing_error", trace_info=data.get("ip_address", ""), message=f"Failed to process image: {str(e)}", secure=False)
                return jsonify({"message": "Failed to process image"}), 500
        else:
            return jsonify({"message": "Image file is required"}), 400
        
        # Helper function to get form data
        def get_field(key: str, default: str = '') -> str:
            return data.get(key, default).strip()
        
        # Validate and fill fields based on account type
        if acc_type == 'students':
            required_fields = [
                'name_en', 'name_bn', 'name_ar', 'date_of_birth',
                'birth_certificate', 'blood_group', 'gender',
                'source', 'present_address', 'present_address_hash', 'present_address_encrypted',
                'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
                'father_en', 'father_bn', 'father_ar',
                'mother_en', 'mother_bn', 'mother_ar',
                'class', 'phone', 'student_id', 'guardian_number'
            ]
            
            missing_required = [field for field in required_fields if not get_field(field)]
            if missing_required:
                return jsonify({
                    "message": _("All required fields must be provided for Student")
                }), 400
            
            fields.update({field: get_field(field) for field in required_fields})
            
        elif acc_type in ['teachers', 'admins']:
            required_fields = [
                'name_en', 'name_bn', 'name_ar', 'date_of_birth',
                'national_id', 'blood_group', 'gender',
                'title1', 'present_address', 'present_address_hash', 'present_address_encrypted',
                'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
                'father_en', 'father_bn', 'father_ar',
                'mother_en', 'mother_bn', 'mother_ar',
                'phone'
            ]
            
            missing_required = [field for field in required_fields if not get_field(field)]
            if missing_required:
                return jsonify({
                    "message": _("All required fields must be provided for %(type)s") % {"type": acc_type}
                }), 400
            
            fields.update({field: get_field(field) for field in required_fields})
            
            # Add optional fields
            optional_fields = ["degree"]
            fields.update({field: get_field(field) for field in optional_fields if get_field(field)})
            
        elif acc_type == 'staffs':
            required_fields = [
                'name_en', 'name_bn', 'name_ar', 'date_of_birth',
                'national_id', 'blood_group',
                'title2', 'present_address', 'present_address_hash', 'present_address_encrypted',
                'permanent_address', 'permanent_address_hash', 'permanent_address_encrypted',
                'father_en', 'father_bn', 'father_ar',
                'mother_en', 'mother_bn', 'mother_ar',
                'phone'
            ]
            
            missing_required = [field for field in required_fields if not get_field(field)]
            if missing_required:
                return jsonify({
                    "message": _("All required fields must be provided for %(type)s") % {"type": acc_type}
                }), 400
            
            fields.update({field: get_field(field) for field in required_fields})
            
        else:  # others, donors, badri_members
            basic_required = ['name_en', 'phone', 'father_or_spouse', 'date_of_birth']
            missing_basic = [field for field in basic_required if not get_field(field)]
            
            if missing_basic:
                return jsonify({
                    "message": _("Name, Phone, and Father/Spouse are required for Guest")
                }), 400
            
            fields.update({
                "name_en": get_field("name_en"),
                "phone": get_field("phone"),
                "father_or_spouse": get_field("father_or_spouse"),
                "date_of_birth": get_field("date_of_birth")
            })
            
            # Add optional fields
            optional_fields = [
                "source", "present_address", "present_address_hash", "present_address_encrypted",
                "blood_group", "gender", "degree"
            ]
            fields.update({field: get_field(field) for field in optional_fields if get_field(field)})
        
        # Encrypt sensitive fields
        encrypted_fields = ["national_id_encrypted", "birth_certificate_encrypted"]
        hash_fields = ["present_address_hash", "permanent_address_hash", "address_hash"]
        
        for field in encrypted_fields:
            if field in fields and fields[field]:
                fields[field] = encrypt_sensitive_data(str(fields[field]))
        
        for field in hash_fields:
            if field in fields and fields[field]:
                fields[field] = hash_sensitive_data(str(fields[field]))
        
        # Insert into database
        await insert_person(madrasa_name, fields, acc_type, formatted_phone)
        
        # Invalidate related cache
        invalidate_related_cache('add_person', user_id=person_id)
        
        # Get image path for response
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(
                f"SELECT image_path FROM {madrasa_name}.peoples WHERE LOWER(name) = %s AND phone = %s",
                (fullname.lower(), formatted_phone)
            )
            row = await cursor.fetchone()
            img_path = row["image_path"] if row else None
        
        # Log successful addition
        log_operation_success("add_person", {
            "fullname": fullname,
            "acc_type": acc_type,
            "user_id": person_id
        })
        
        return jsonify({
            "success": True,
            "message": _("%(type)s profile added successfully") % {"type": acc_type},
            "user_id": person_id,
            "info": img_path
        }), 201
        
    except Exception as e:
        log.critical(action="add_person_error", trace_info="system", message=f"Error adding person: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['internal_error']}), 500

@api.route('/members', methods=['POST'])
@cache_with_invalidation
@handle_async_errors
async def get_info() -> Tuple[Response, int]:
    """Get member information with caching and incremental updates"""
    try:
        # Get request data
        data = await request.get_json() # TODO: Validate request data
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        madrasa_name = os.getenv("MADRASA_NAME")
        lastfetched = data.get('updatedSince')
        
        # Process timestamp using enhanced validation
        corrected_time = None
        if lastfetched:
            try:
                corrected_time = lastfetched.replace("T", " ").replace("Z", "")
            except Exception as e:
                log.warning(action="timestamp_processing_error", trace_info=data.get("ip_address", ""), message=f"Error processing timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid timestamp format"}), 400
        
        # Build SQL query with proper joins
        sql = f"""
            SELECT 
                tname.translation_text AS name_en, 
                tname.bn_text AS name_bn, 
                tname.ar_text AS name_ar,
                taddress.translation_text AS address_en, 
                taddress.bn_text AS address_bn, 
                taddress.ar_text AS address_ar,
                tfather.translation_text AS father_en, 
                tfather.bn_text AS father_bn, 
                tfather.ar_text AS father_ar,
                p.degree, p.gender, p.blood_group,
                p.phone, p.image_path AS picUrl, p.member_id, p.acc_type AS role,
                COALESCE(p.title1, p.title2, p.class) AS title,
                a.main_type AS acc_type, 
                a.teacher, a.student, a.staff, a.donor, 
                a.badri_member, a.special_member
            FROM {madrasa_name}.peoples p
            JOIN global.acc_types a ON a.user_id = p.user_id
            JOIN global.translations tname ON tname.translation_text = p.name
            LEFT JOIN global.translations taddress ON taddress.translation_text = p.address
            LEFT JOIN global.translations tfather ON tfather.translation_text = p.father_name
            WHERE p.member_id IS NOT NULL
        """
        
        params = []
        if corrected_time:
            sql += " AND p.updated_at > %s"
            params.append(corrected_time)
        
        sql += " ORDER BY p.member_id"
        
        # Execute query with enhanced cache management
        cache_key = get_cache_key("members", lastfetched=lastfetched)
        cached_members = await get_cached_data(cache_key)
        
        if cached_members is not None:
            return jsonify(cached_members), 200
        
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(sql, params)
            members = await cursor.fetchall()
        
        # Cache the result
        result_data = {
            "members": members,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        await set_cached_data(cache_key, result_data, ttl=config.SHORT_CACHE_TTL)
        
        # Log successful retrieval
        log_operation_success("get_members", {
            "count": len(members),
            "lastfetched": lastfetched
        })
        
        return jsonify(result_data), 200
        
    except Exception as e:
        log.critical(action="get_members_error", trace_info="system", message=f"Error retrieving members: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['database_error']}), 500

@api.route("/routines", methods=["POST"])
@cache_with_invalidation
@handle_async_errors
async def get_routine() -> Tuple[Response, int]:
    """Get routine information with caching and incremental updates"""
    # Check maintenance mode
    if config.is_maintenance:
        return jsonify({
            "error": ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_client_info()
    
    try:
        # Get request data
        data = await request.get_json()
        if not data:
            return jsonify({"error": "Invalid request data"}), 400
        
        madrasa_name = os.getenv("MADRASA_NAME")
        lastfetched = data.get("updatedSince")
        
        # Process timestamp using enhanced validation
        corrected_time = None
        if lastfetched:
            if not validate_timestamp_format(lastfetched):
                log.warning(action="invalid_routine_timestamp", trace_info=data.get("ip_address", ""), message=f"Invalid timestamp format: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid timestamp format"}), 400
            try:
                corrected_time = lastfetched.replace("T", " ").replace("Z", "")
            except Exception as e:
                log.warning(action="routine_timestamp_processing_error", trace_info=data.get("ip_address", ""), message=f"Error processing timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid timestamp format"}), 400
        
        # Build SQL query
        sql = f"""
            SELECT 
                r.gender, r.class_group, r.class_level, r.weekday, r.serial,
                tsubject.translation_text AS subject_en, 
                tsubject.bn_text AS subject_bn, 
                tsubject.ar_text AS subject_ar, 
                tname.translation_text AS name_en, 
                tname.bn_text AS name_bn, 
                tname.ar_text AS name_ar 
            FROM {madrasa_name}.routines r
            JOIN global.translations tsubject ON tsubject.translation_text = r.subject 
            JOIN global.translations tname ON tname.translation_text = r.name
        """
        
        params = []
        if corrected_time:
            sql += " WHERE r.updated_at > %s"
            params.append(corrected_time)
        
        sql += " ORDER BY r.class_level, r.weekday, r.serial"
        
        # Execute query with enhanced cache management
        cache_key = get_cache_key("routines", lastfetched=lastfetched)
        cached_routines = await get_cached_data(cache_key)
        
        if cached_routines is not None:
            return jsonify(cached_routines), 200
        
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
        
        # Cache the result
        result_data = {
            "routines": result,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        await set_cached_data(cache_key, result_data, ttl=config.SHORT_CACHE_TTL)
        
        # Log successful retrieval
        log_operation_success("get_routines", {
            "count": len(result),
            "lastfetched": lastfetched
        })
        
        return jsonify(result_data), 200
        
    except Exception as e:
        log.critical(action="get_routines_error", trace_info="system", message=f"Error retrieving routines: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['database_error']}), 500

@api.route('/events', methods=['POST'])
@cache_with_invalidation
@handle_async_errors
async def events() -> Tuple[Response, int]:
    """
    Get events with enhanced date processing and status classification
    
    Returns:
        JSON response with events data and sync timestamp
    """
    # Check maintenance mode
    if config.is_maintenance:
        return jsonify({
            "error": ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_client_info()
    
    try:
        # Get request data
        data = await request.get_json() or {}
        madrasa_name = os.getenv("MADRASA_NAME")
        lastfetched = data.get('updatedSince')
        DHAKA = ZoneInfo("Asia/Dhaka")
        
        # Build SQL query
        sql = f"""
            SELECT 
                e.type, e.time, e.date, e.function_url,
                ttitle.translation_text AS title_en, 
                ttitle.bn_text AS title_bn, 
                ttitle.ar_text AS title_ar
            FROM {madrasa_name}.events e
            JOIN global.translations ttitle ON ttitle.translation_text = e.title
        """
        
        params = []
        if lastfetched:
            if not validate_timestamp_format(lastfetched):
                log.error(action="get_events_failed", trace_info=data.get("ip_address", ""), message=f"Invalid timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid updatedSince format"}), 400
            try:
                cutoff = datetime.fromisoformat(lastfetched.replace("Z", "+00:00"))
                sql += " WHERE e.created_at > %s"
                params.append(cutoff)
            except ValueError as e:
                log.error(action="events_timestamp_processing_error", trace_info=data.get("ip_address", ""), message=f"Error processing timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid updatedSince format"}), 400
        
        sql += " ORDER BY e.event_id DESC"
        
        # Execute query with enhanced cache management
        cache_key = get_cache_key("events", lastfetched=lastfetched)
        cached_events = await get_cached_data(cache_key)
        
        if cached_events is not None:
            return jsonify(cached_events), 200
        
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(sql, params)
            rows = await cursor.fetchall()
        
        # Process events with date classification
        now_dhaka = datetime.now(DHAKA)
        today = now_dhaka.date()
        
        for ev in rows:
            ev_dt = ev.get("date") or ev.get("event_date")
            
            if isinstance(ev_dt, datetime):
                ev_dt_local = ev_dt.astimezone(DHAKA)
                ev_date = ev_dt_local.date()
                ev["date"] = ev_dt_local.isoformat()
            elif isinstance(ev_dt, date):
                ev_date = ev_dt
                ev["date"] = ev_dt.isoformat()
            else:
                ev_date = None
            
            # Classify event status
            if ev_date:
                if ev_date > today:
                    ev["type"] = "upcoming"
                elif ev_date == today:
                    ev["type"] = "ongoing"
                else:
                    ev["type"] = "past"
            else:
                ev["status"] = "unknown"
        
        # Cache the result
        result_data = {
            "events": rows,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        await set_cached_data(cache_key, result_data, ttl=config.SHORT_CACHE_TTL)
        
        # Log successful retrieval
        log_operation_success("get_events", {
            "count": len(rows),
            "lastfetched": lastfetched
        })
        
        return jsonify(result_data), 200
        
    except Exception as e:
        log.critical(action="get_events_error", trace_info="system", message=f"Error retrieving events: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['database_error']}), 500

@api.route('/exams', methods=['POST'])
@cache_with_invalidation
@handle_async_errors
async def get_exams() -> Tuple[Response, int]:
    """Get exam information with enhanced validation and error handling"""
    # Check maintenance mode
    if config.is_maintenance:
        return jsonify({
            "error": ERROR_MESSAGES['maintenance_mode']
        }), 503
    
    # Get client info for logging
    # client_info = get_client_info()
    
    try:
        # Get request data
        data, error = await secure_data()
        if not data:
            return jsonify({"error": error}), 400
        
        madrasa_name = os.getenv("MADRASA_NAME")
        lastfetched = data.get("updatedSince")
        
        # Process timestamp using enhanced validation
        cutoff = None
        if lastfetched:
            if not validate_timestamp_format(lastfetched):
                log.error(action="get_exams_failed", trace_info=data.get("ip_address", ""), message=f"Invalid timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid updatedSince format"}), 400
            try:
                cutoff = lastfetched.replace("T", " ").replace("Z", "")
            except Exception as e:
                log.error(action="exams_timestamp_processing_error", trace_info=data.get("ip_address", ""), message=f"Error processing timestamp: {lastfetched}", secure=False)
                return jsonify({"error": "Invalid updatedSince format"}), 400
        
        # Build SQL query
        sql = f"""
            SELECT 
                e.class, e.gender, e.start_time, e.end_time, e.date, e.weekday, 
                e.sec_start_time, e.sec_end_time,
                tbook.translation_text AS book_en, 
                tbook.bn_text AS book_bn, 
                tbook.ar_text AS book_ar
            FROM {madrasa_name}.exams e
            JOIN global.translations tbook ON tbook.translation_text = e.book
        """
        
        params = []
        if cutoff:
            sql += " WHERE e.created_at > %s"
            params.append(cutoff)
        
        sql += " ORDER BY e.exam_id"
        
        # Execute query with enhanced cache management
        cache_key = get_cache_key("exams", lastfetched=lastfetched)
        cached_exams = await get_cached_data(cache_key)
        
        if cached_exams is not None:
            return jsonify(cached_exams), 200
        
        conn = await get_db_connection()
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from observability.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
        
        # Cache the result
        result_data = {
            "exams": result,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }
        await set_cached_data(cache_key, result_data, ttl=config.SHORT_CACHE_TTL)
        
        # Log successful retrieval
        log_operation_success("get_exams", {
            "count": len(result),
            "lastfetched": lastfetched
        })
        
        return jsonify(result_data), 200
        
    except Exception as e:
        log.critical(action="get_exams_error", trace_info="system", message=f"Error retrieving exams: {str(e)}", secure=False)
        return jsonify({"message": ERROR_MESSAGES['database_error']}), 500





# ─── Request Processing Middleware ───────────────────────────────────────────

async def process_request_middleware(request: Request) -> Tuple[bool, str]:
    """Process request with security and validation checks"""
    # Check maintenance mode
    if config.is_maintenance:
        return False, ERROR_MESSAGES['maintenance_mode']
    
    # Validate request origin
    if not validate_request_origin(request):
        return False, "Invalid request origin"
    
    # Check for suspicious activity
    client_info = get_client_info()
    if security_manager.detect_sql_injection(str(request.url)):
        await security_manager.track_suspicious_activity(
            client_info["ip_address"], 
            "SQL injection in URL"
        )
        return False, "Suspicious request detected"
    
    return True, ""

# ─── Response Enhancement ─────────────────────────────────────────────────────

def enhance_response_headers(response: Response) -> Response:
    """Add security and performance headers to response"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ─── Database Connection Management ───────────────────────────────────────────

def validate_timestamp_format(timestamp: str) -> bool:
    """Validate timestamp format"""
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False



def log_operation_success(operation: str, details: Dict[str, Any]) -> None:
    """Log successful operation with details"""
    log.info(action=f"{operation}_success", trace_info=get_client_info()["ip_address"], message=f"Operation {operation} completed successfully", secure=False, **details)

def log_operation_failure(operation: str, error: Exception, details: Dict[str, Any] | None = None) -> None:
    """Log failed operation with error details"""
    if details is None:
        details = {}
    
    log.critical(action=f"{operation}_failure", trace_info=get_client_info()["ip_address"], message=f"Operation {operation} failed: {str(error)}", secure=False, **details)

def validate_folder_access(folder: str, allowed_folders: List[str]) -> bool:
    """Validate folder access permissions"""
    return folder in allowed_folders