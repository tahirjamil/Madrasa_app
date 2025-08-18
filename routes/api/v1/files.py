# ─── Enhanced File Serving Routes ───────────────────────────────────────────
from fastapi import Request, HTTPException, Depends
from fastapi.responses import FileResponse
from typing import Tuple
import os
import re

from utils.helpers.improved_functions import send_json_response
from utils.helpers.fastapi_helpers import ClientInfo, validate_device_dependency, handle_async_errors, get_client_info
from api import api
from utils.helpers.logger import log
from config import config

ERROR_MESSAGES = {
        'file_not_found': "File not found",
        'invalid_folder': "Invalid folder name",
        'invalid_gender': "Invalid gender parameter",
        'file_too_large': "File size exceeds maximum allowed size",
        'invalid_file_type': "Invalid file type",
        'unauthorized': "Unauthorized access",
        'internal_error': "An internal error occurred",
    }

# ─── Security and Validation Functions ───────────────────────────────────────

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for security"""
    if not filename:
        return ""
    
    # Remove path traversal attempts
    filename = filename.replace('..', '').replace('/', '').replace('\\', '')
    
    # Remove potentially dangerous characters
    filename = re.sub(r'[<>:"|?*]', '', filename)
    
    # Ensure filename is not empty after sanitization
    if not filename.strip():
        return "default"
    
    # Use a simple secure filename implementation
    # Remove non-alphanumeric characters except dots, hyphens, and underscores
    filename = re.sub(r'[^\w\s.-]', '', filename).strip()
    filename = re.sub(r'[-\s]+', '-', filename)
    
    return filename

def validate_folder_access(folder: str, allowed_folders: list) -> bool:
    """Validate folder access against allowed folders list"""
    # Sanitize folder name
    sanitized_folder = folder.strip()
    
    # Check for path traversal attempts
    if '..' in sanitized_folder or '/' in sanitized_folder or '\\' in sanitized_folder:
        return False
    
    # Check if folder is in allowed list
    return sanitized_folder in allowed_folders

def get_safe_file_path(base_path: str, filename: str) -> Tuple[str, str] | Tuple[None, None]:
    """Get safe file path and validate existence"""
    safe_filename = sanitize_filename(filename)
    file_path = os.path.join(base_path, safe_filename)
    
    # Additional security check - ensure path is within base directory
    try:
        real_base_path = os.path.realpath(base_path)
        real_file_path = os.path.realpath(file_path)
        
        if not real_file_path.startswith(real_base_path):
            raise ValueError("Path traversal detected")
            
    except (OSError, ValueError) as e:
        log.critical(action="path_traversal_attempt", trace_info=filename, message=f"Path traversal attempt: {str(e)}", secure=False)
        return None, None
    
    return file_path, safe_filename

# ─── File Serving Routes ───────────────────────────────────────────────────────

@api.get('/uploads/profile_img/{filename}')
@handle_async_errors
async def uploaded_file(
    filename: str,
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
) -> FileResponse:
    """Serve user profile images with enhanced security"""
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(config.PROFILE_IMG_UPLOAD_FOLDER, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_profile_image_request", trace_info=client_info.ip_address, message=f"Invalid filename: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Check if file exists and is accessible
    if not os.path.isfile(file_path):
        log.warning(action="profile_image_not_found", trace_info=client_info.ip_address, message=f"Profile image not found: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Validate file type
    if not safe_filename or not any(safe_filename.lower().endswith(ext) for ext in config.ALLOWED_IMAGE_EXTENSIONS):
        log.warning(action="invalid_image_type", trace_info=client_info.ip_address, message=f"Invalid image type: {filename}", secure=False)
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['invalid_file_type'])
    
    try:
        # Serve file with security headers
        response = FileResponse(
            path=file_path,
            media_type="image/jpeg", # Default to JPEG, adjust if needed
            filename=safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        # Log successful access
        log.info(action="profile_image_served", trace_info=client_info.ip_address, message=f"Profile image served: {safe_filename}", secure=False)
        
        return response
        
    except Exception as e:
        log.critical(action="file_serving_error", trace_info=client_info.ip_address, message=f"Error serving file {filename}: {str(e)}", secure=False)
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES['internal_error'])

@api.get('/uploads/notices/{filename}')
@handle_async_errors
async def notices_file(
    filename: str,
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
) -> FileResponse:
    """Serve notice files with enhanced security"""
    
    # Get upload folder from config
    upload_folder = config.NOTICES_UPLOAD_FOLDER
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_notice_request", trace_info=client_info.ip_address, message=f"Invalid filename: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="notice_file_not_found", trace_info=client_info.ip_address, message=f"Notice file not found: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    try:
        # Serve file with security headers
        response = FileResponse(
            path=file_path,
            media_type="application/pdf", # Default to PDF, adjust if needed
            filename=safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=1800'  # 30 minutes
        
        # Log successful access
        log.info(action="notice_file_served", trace_info=client_info.ip_address, message=f"Notice file served: {safe_filename}", secure=False)
        
        return response
        
    except Exception as e:
        log.critical(action="notice_serving_error", trace_info=client_info.ip_address, message=f"Error serving notice file {filename}: {str(e)}", secure=False)
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES['internal_error'])

@api.get('/uploads/exam_results/{filename}')
@handle_async_errors
async def exam_results_file(
    filename: str,
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
) -> FileResponse:
    """Serve exam result files with enhanced security"""
    
    # Get upload folder from config
    upload_folder = config.EXAM_RESULTS_UPLOAD_FOLDER
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_exam_result_request", trace_info=client_info.ip_address, message=f"Invalid filename: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="exam_result_file_not_found", trace_info=client_info.ip_address, message=f"Exam result file not found: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    try:
        # Serve file with security headers
        response = FileResponse(
            path=file_path,
            media_type="application/pdf", # Default to PDF, adjust if needed
            filename=safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
        
        # Log successful access
        log.info(action="exam_result_file_served", trace_info=client_info.ip_address, message=f"Exam result file served: {safe_filename}", secure=False)
        
        return response
        
    except Exception as e:
        log.critical(action="exam_result_serving_error", trace_info=client_info.ip_address, message=f"Error serving exam result file {filename}: {str(e)}", secure=False)
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES['internal_error'])

@api.get('/uploads/gallery/{gender}/{folder}/{filename}')
@handle_async_errors
async def gallery_file(
    gender: str,
    folder: str,
    filename: str,
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
) -> FileResponse:
    """Serve gallery files with enhanced security and validation"""
    
    # Validate gender parameter
    if gender not in config.ALLOWED_GALLERY_GENDERS:
        log.warning(action="invalid_gallery_gender", trace_info=client_info.ip_address, message=f"Invalid gender parameter: {gender}", secure=False)
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['invalid_gender'])
    
    # Validate folder parameter
    if not validate_folder_access(folder, config.ALLOWED_GALLERY_FOLDERS):
        log.warning(action="invalid_gallery_folder", trace_info=client_info.ip_address, message=f"Invalid folder parameter: {folder}", secure=False)
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['invalid_folder'])
    
    # Get upload folder path
    upload_folder = os.path.join(
        request.app.config['BASE_UPLOAD_FOLDER'], 
        'gallery', gender, folder
    )
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_gallery_file_request", trace_info=client_info.ip_address, message=f"Invalid filename: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="gallery_file_not_found", trace_info=client_info.ip_address, message=f"Gallery file not found: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    try:
        # Serve file with security headers
        response = FileResponse(
            path=file_path,
            media_type="image/jpeg", # Default to JPEG, adjust if needed
            filename=safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=7200'  # 2 hours
        
        # Log successful access
        log.info(action="gallery_file_served", trace_info=client_info.ip_address, message=f"Gallery file served: {gender}/{folder}/{safe_filename}", secure=False)
        
        return response
        
    except Exception as e:
        log.critical(action="gallery_serving_error", trace_info=client_info.ip_address, message=f"Error serving gallery file {filename}: {str(e)}", secure=False)
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES['internal_error'])

@api.get('/uploads/gallery/classes/{folder}/{filename}')
@handle_async_errors
async def gallery_classes_file(
    folder: str,
    filename: str,
    request: Request,
    client_info: ClientInfo = Depends(get_client_info)
) -> FileResponse:
    """Serve gallery class files with enhanced security and validation"""
    
    # Validate folder parameter
    if not validate_folder_access(folder, config.ALLOWED_CLASS_FOLDERS):
        log.warning(action="invalid_class_folder", trace_info=client_info.ip_address, message=f"Invalid class folder parameter: {folder}", secure=False)
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['invalid_folder'])
    
    # Get upload folder path
    upload_folder = os.path.join(
        request.app.config['BASE_UPLOAD_FOLDER'], 
        'gallery', 'classes', folder
    )
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_class_file_request", trace_info=client_info.ip_address, message=f"Invalid filename: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="class_file_not_found", trace_info=client_info.ip_address, message=f"Class file not found: {filename}", secure=False)
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['file_not_found'])
    
    try:
        # Serve file with security headers
        response = FileResponse(
            path=file_path,
            media_type="application/pdf", # Default to PDF, adjust if needed
            filename=safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=7200'  # 2 hours
        
        # Log successful access
        log.info(action="class_file_served", trace_info=client_info.ip_address, message=f"Class file served: {folder}/{safe_filename}", secure=False)
        
        return response
        
    except Exception as e:
        log.critical(action="class_file_serving_error", trace_info=client_info.ip_address, message=f"Error serving class file {filename}: {str(e)}", secure=False)
        raise HTTPException(status_code=500, detail=ERROR_MESSAGES['internal_error'])
