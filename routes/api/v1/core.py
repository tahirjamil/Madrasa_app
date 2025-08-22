import os
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from PIL import Image
from fastapi import Request, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, field_validator
from werkzeug.utils import secure_filename

from utils.helpers.improved_functions import get_env_var, send_json_response
from utils.helpers.fastapi_helpers import BaseAuthRequest, ClientInfo, validate_device_dependency, rate_limit

# Local imports
from routes.api import api
from utils.mysql.database_utils import get_traced_db_cursor
from config import config
from utils.helpers.helpers import (
    format_phone_number, get_global_id, get_id, insert_person, get_cache_key,
    cache_with_invalidation, security_manager, set_cached_data, get_cached_data, handle_async_errors,
    encrypt_sensitive_data, hash_sensitive_data, validate_file_upload, validate_fullname, validate_madrasa_name, validate_request_origin
)
from utils.helpers.logger import log

# ─── Pydantic Models ───────────────────────────────────────────────
class BaseRouteData(BaseModel):
    madrasa_name: str
    updatedSince: Optional[str] = None

    @field_validator('madrasa_name')
    def validate_madrasa_name(cls, v):
        validate_madrasa_name(v, "system", secure=False)
        return v

class PersonData(BaseAuthRequest):
    """Person data model for adding/updating people"""
    student_id: Optional[str] = None
    name: str
    email: Optional[str] = None
    birth_date: Optional[str] = None
    blood_group: Optional[str] = None
    gender: str
    address: Optional[str] = None
    guardian_number: Optional[str] = None
    class_name: Optional[str] = None
    monthly_fee: Optional[float] = None
    
    @field_validator('name')
    def validate_name_field(cls, v):
        validate_fullname(v)
        return v

class ProfileUpdateRequest(BaseAuthRequest):
    """Profile update request model"""
    field: str
    value: str

# ─── Configuration and Constants ───────────────────────────────────────────────

ERROR_MESSAGES = {
        'invalid_phone': "Invalid phone number format",
        'invalid_name': "Invalid name format",
        'rate_limit_exceeded': "Rate limit exceeded. Please try again later.",
        'maintenance_mode': "Application is currently in maintenance mode",
        'unauthorized': "Unauthorized access",
        'internal_error': "An internal error occurred",
        'validation_error': "Validation error",
        'database_error': "Database operation failed"
    }

# ─── Data Management Routes ─────────────────────────────────────────────────

@api.post('/add_people')
@rate_limit(max_requests=config.STRICT_RATE_LIMIT, window=3600)
@handle_async_errors
async def add_person(
    request: Request,
    # Form fields
    name_en: str = Form(...),
    phone: str = Form(...),
    acc_type: str = Form(...),
    madrasa_name: Optional[str] = Form(None),
    # Optional form fields based on acc_type
    name_bn: Optional[str] = Form(None),
    name_ar: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    birth_certificate: Optional[str] = Form(None),
    national_id: Optional[str] = Form(None),
    blood_group: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    present_address: Optional[str] = Form(None),
    permanent_address: Optional[str] = Form(None),
    father_en: Optional[str] = Form(None),
    father_bn: Optional[str] = Form(None),
    father_ar: Optional[str] = Form(None),
    mother_en: Optional[str] = Form(None),
    mother_bn: Optional[str] = Form(None),
    mother_ar: Optional[str] = Form(None),
    student_id: Optional[str] = Form(None),
    guardian_number: Optional[str] = Form(None),
    class_field: Optional[str] = Form(None, alias="class"),
    title1: Optional[str] = Form(None),
    title2: Optional[str] = Form(None),
    degree: Optional[str] = Form(None),
    father_or_spouse: Optional[str] = Form(None),
    teacher: Optional[str] = Form("0"),
    student: Optional[str] = Form("0"),
    staff: Optional[str] = Form("0"),
    donor: Optional[str] = Form("0"),
    badri_member: Optional[str] = Form("0"),
    special_member: Optional[str] = Form("0"),
    # File upload
    image: Optional[UploadFile] = File(None),
    # Dependencies
    client_info: ClientInfo = Depends(validate_device_dependency)
) -> JSONResponse:
    """Add a new person to the system with comprehensive validation and security """
    try:
        # Use the provided madrasa_name or get from env
        madrasa_name = madrasa_name or get_env_var("MADRASA_NAME")
        
        # Ensure madrasa_name is not None before validation
        if not madrasa_name:
            response, status = send_json_response("Madrasa name is required", 400)
            return JSONResponse(content=response, status_code=status)
        
        # SECURITY: Validate madrasa_name is in allowed list
        if not validate_madrasa_name(madrasa_name, phone, secure=True):
            response, status = send_json_response(ERROR_MESSAGES['unauthorized'], 401)
            return JSONResponse(content=response, status_code=status)
        
        # Extract and validate basic fields with sanitization
        fullname = name_en
        
        # Validate fullname
        validate_fullname(fullname)
        
        # Validate and format phone number
        formatted_phone = format_phone_number(phone)
        
        # Normalize account type
        if not acc_type or not acc_type.endswith('s'):
            acc_type = f"{acc_type}s"
        
        VALID_ACCOUNT_TYPES = [
            'admins', 'students', 'teachers', 'staffs', 
            'others', 'badri_members', 'donors'
        ]
        if acc_type not in VALID_ACCOUNT_TYPES:
            acc_type = 'others'
        
        # Get user ID
        person_id = await get_global_id(formatted_phone, fullname)
        if not person_id:
            log.error(action="add_people_id_not_found", trace_info=formatted_phone, message="User ID not found", secure=True)
            response, status = send_json_response("ID not found", 404)
            return JSONResponse(content=response, status_code=status)
        
        # Initialize fields dictionary
        fields: Dict[str, Any] = {"user_id": person_id}
        
        # Set account type boolean fields
        fields.update({
            "teacher": teacher == '1' or acc_type == 'teachers',
            "student": student == '1' or acc_type == 'students',
            "staff": staff == '1' or acc_type == 'staffs',
            "donor": donor == '1' or acc_type == 'donors',
            "badri_member": badri_member == '1' or acc_type == 'badri_members',
            "special_member": special_member == '1'
        })
        
        # Handle image upload with enhanced security
        if image and image.filename:
            # Validate file upload
            await validate_file_upload(
                file=image,
                allowed_extensions=list(config.ALLOWED_PROFILE_IMG_EXTENSIONS),
                request=request
            )
            
            # Generate secure filename
            filename_base = f"{person_id}_{os.path.splitext(secure_filename(image.filename))[0]}"
            filename = filename_base + ".webp"
            upload_folder = config.PROFILE_IMG_UPLOAD_FOLDER
            image_path = os.path.join(upload_folder, filename)
            
            try:
                # Process and save image
                img = Image.open(image.file)
                img.verify()  # Verify image integrity
                image.file.seek(0)
                img = Image.open(image.file)
                
                # Convert to RGB if necessary
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                
                # Save as WebP for better compression
                img.save(image_path, "WEBP", quality=config.PROFILE_IMG_QUALITY)
                
                # Set image path
                fields["image_path"] = f"{config.BASE_URL}/uploads/profile_pics/{filename}"
                
            except Exception as e:
                log.critical(action="image_processing_error", trace_info=client_info.ip_address, message=f"Failed to process image: {str(e)}", secure=False)
                response, status = send_json_response("Failed to process image", 500)
                return JSONResponse(content=response, status_code=status)
        else:
            response, status = send_json_response("Image file is required", 400)
            return JSONResponse(content=response, status_code=status)
        
        # Create a dictionary from form fields for easier processing
        form_data = {
            'name_en': name_en,
            'name_bn': name_bn,
            'name_ar': name_ar,
            'date_of_birth': date_of_birth,
            'birth_certificate': birth_certificate,
            'national_id': national_id,
            'blood_group': blood_group,
            'gender': gender,
            'source': source,
            'present_address': present_address,
            'present_address_hash': present_address,  # Will be hashed later
            'present_address_encrypted': present_address,  # Will be encrypted later
            'permanent_address': permanent_address,
            'permanent_address_hash': permanent_address,  # Will be hashed later
            'permanent_address_encrypted': permanent_address,  # Will be encrypted later
            'father_en': father_en,
            'father_bn': father_bn,
            'father_ar': father_ar,
            'mother_en': mother_en,
            'mother_bn': mother_bn,
            'mother_ar': mother_ar,
            'student_id': student_id,
            'guardian_number': guardian_number,
            'class': class_field,
            'title1': title1,
            'title2': title2,
            'degree': degree,
            'father_or_spouse': father_or_spouse,
            'phone': phone
        }
        
        # Helper function to get form data
        def get_field(key: str, default: str = '') -> str:
            value = form_data.get(key, default)
            return value.strip() if value else default
        
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
                response, status = send_json_response("All required fields must be provided for Student", 400)
                return JSONResponse(content=response, status_code=status)
            
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
                response, status = send_json_response(f"All required fields must be provided for {acc_type}", 400)
                return JSONResponse(content=response, status_code=status)
            
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
                response, status = send_json_response(f"All required fields must be provided for {acc_type}", 400)
                return JSONResponse(content=response, status_code=status)
            
            fields.update({field: get_field(field) for field in required_fields})
            
        else:  # others, donors, badri_members
            basic_required = ['name_en', 'phone', 'father_or_spouse', 'date_of_birth']
            missing_basic = [field for field in basic_required if not get_field(field)]
            
            if missing_basic:
                response, status = send_json_response("Name, Phone, and Father/Spouse are required for Guest", 400)
                return JSONResponse(content=response, status_code=status)
            
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
        
        # Insert into database (madrasa_name is guaranteed to be not None at this point)
        await insert_person(madrasa_name, fields, acc_type, formatted_phone)
        
        # Get image path for response
        async with get_traced_db_cursor() as cursor:
                await cursor.execute(
                    f"SELECT image_path FROM {madrasa_name}.peoples WHERE LOWER(name) = %s AND phone = %s",
                    (fullname.lower(), formatted_phone)
                )
                row = await cursor.fetchone()
                img_path = row["image_path"] if row else None
        
        # Log successful addition
        log.info(action="add_person", trace_info=formatted_phone, message=f"User {fullname} added successfully", secure=True)
        
        response, status = send_json_response(f"{acc_type} profile added successfully", 201)
        response.update({"user_id": person_id, "info": img_path})
        return JSONResponse(content=response, status_code=status)
        
    except Exception as e:
        log.critical(action="add_person_error", trace_info="system", message=f"Error adding person: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return JSONResponse(content=response, status_code=status)

@api.post('/members')
@cache_with_invalidation
@handle_async_errors
async def get_info(data: BaseRouteData, client_info: ClientInfo = Depends(validate_device_dependency)) -> JSONResponse:
    """Get member information with caching and incremental updates"""
    async with get_traced_db_cursor() as cursor:
        # Get request data from request body
        madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
        lastfetched = data.updatedSince

        # Process timestamp using enhanced validation
        corrected_time = None
        if lastfetched:
            try:
                corrected_time = lastfetched.replace("T", " ").replace("Z", "")
            except Exception as e:
                log.warning(action="timestamp_processing_error", trace_info=client_info.ip_address, message=f"Error processing timestamp: {lastfetched}", secure=False)
                response, status = send_json_response("Invalid timestamp format", 400)
                return JSONResponse(content=response, status_code=status)
        
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
        
        await cursor.execute(sql, params)
        members = await cursor.fetchall()
        
        # Cache the result
        result_data = {
            "members": members,
            "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        }        
        return JSONResponse(content=result_data, status_code=200)
        

@api.post("/routines")
@cache_with_invalidation
@handle_async_errors
async def get_routine(data: BaseRouteData, client_info: ClientInfo = Depends(validate_device_dependency)) -> JSONResponse:
    """Get routine information with caching and incremental updates"""
    # Get request data from request body
    madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
    lastfetched = data.updatedSince

    # Process timestamp using enhanced validation
    cutoff = None
    if lastfetched:
        cutoff =  validate_timestamp_format(lastfetched, client_info.ip_address)
    
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
    if cutoff:
        sql += " WHERE r.updated_at > %s"
        params.append(cutoff)
    
    sql += " ORDER BY r.class_level, r.weekday, r.serial"
    
    async with get_traced_db_cursor() as cursor:
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
    
    result_data = {
        "routines": result,
        "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
            
    return JSONResponse(content=result_data, status_code=200)

@api.post('/events')
@cache_with_invalidation
@handle_async_errors
async def events(data: BaseRouteData, client_info: ClientInfo = Depends(validate_device_dependency)) -> JSONResponse:
    """Get events with enhanced date processing and status classification"""
    # Get request data from request body
    madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
    lastfetched = data.updatedSince
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
        cutoff = validate_timestamp_format(lastfetched, client_info.ip_address)
        sql += " WHERE e.created_at > %s"
        params.append(cutoff)
    
    sql += " ORDER BY e.event_id DESC"
    
    async with get_traced_db_cursor() as cursor:
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
        
        # Log successful retrieval
        log.info(action="get_events", trace_info=client_info.ip_address, message=f"Events retrieved successfully", secure=False)
        
        return JSONResponse(content=result_data, status_code=200)

@api.post('/exams')
@cache_with_invalidation
@handle_async_errors
async def get_exams(data: BaseRouteData, client_info: ClientInfo = Depends(validate_device_dependency)) -> JSONResponse:
    """Get exam information with enhanced validation and error handling"""
    # Get request data from request body
    madrasa_name = data.madrasa_name or get_env_var("MADRASA_NAME")
    lastfetched = data.updatedSince
    
    # Process timestamp using enhanced validation
    cutoff = None
    if lastfetched:
        cutoff = validate_timestamp_format(lastfetched, client_info.ip_address)
        try:
            cutoff = lastfetched.replace("T", " ").replace("Z", "")
        except Exception as e:
            log.error(action="exams_timestamp_processing_error", trace_info=client_info.ip_address, message=f"Error processing timestamp: {lastfetched}", secure=False)
    
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
    
    async with get_traced_db_cursor() as cursor:
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
        
    result_data = {
        "exams": result,
        "lastSyncedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    return JSONResponse(content=result_data, status_code=200)


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

def validate_timestamp_format(timestamp: str, ip_address: str) -> str:
    """Validate timestamp format"""
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return timestamp.replace("T", " ").replace("Z", "")
    except ValueError:
        log.error(action="get_exams_failed", trace_info=ip_address, message=f"Invalid timestamp: {timestamp}", secure=False)
        raise