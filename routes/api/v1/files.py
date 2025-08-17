# ─── Enhanced File Serving Routes ───────────────────────────────────────────
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, Tuple
import os
import re

from utils.helpers.improved_functions import send_json_response
from utils.helpers.fastapi_helpers import ClientInfo, validate_device_dependency, handle_async_errors
from . import api
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

@api.route('/uploads/profile_img/<filename>')
@handle_async_errors
async def uploaded_file(filename: str) -> Tuple[Response, int]:
    """Serve user profile images with enhanced security"""
    # Get client info for logging
    client_info = await get_client_info() or {}
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(config.PROFILE_IMG_UPLOAD_FOLDER, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_profile_image_request", trace_info=client_info["ip_address"], message=f"Invalid filename: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Check if file exists and is accessible
    if not os.path.isfile(file_path):
        log.warning(action="profile_image_not_found", trace_info=client_info["ip_address"], message=f"Profile image not found: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Validate file type
    if not safe_filename or not any(safe_filename.lower().endswith(ext) for ext in config.ALLOWED_IMAGE_EXTENSIONS):
        log.warning(action="invalid_image_type", trace_info=client_info["ip_address"], message=f"Invalid image type: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['invalid_file_type'], 400)
        return jsonify(response), status
    
    try:
        # Serve file with security headers
        response = await send_from_directory(
            config.PROFILE_IMG_UPLOAD_FOLDER, 
            safe_filename
        )
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=3600'
        
        # Log successful access
        log.info(action="profile_image_served", trace_info=client_info["ip_address"], message=f"Profile image served: {safe_filename}", secure=False)
        
        return response, 200
        
    except Exception as e:
        log.critical(action="file_serving_error", trace_info=client_info["ip_address"], message=f"Error serving file {filename}: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return jsonify(response), status

@api.route('/uploads/notices/<path:filename>')
@handle_async_errors
async def notices_file(filename: str) -> Tuple[Response, int]:
    """Serve notice files with enhanced security"""
    # Get client info for logging
    client_info = await get_client_info() or {}
    
    # Get upload folder from config
    upload_folder = config.NOTICES_UPLOAD_FOLDER
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_notice_request", trace_info=client_info["ip_address"], message=f"Invalid filename: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="notice_file_not_found", trace_info=client_info["ip_address"], message=f"Notice file not found: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    try:
        # Serve file with security headers
        response = await send_from_directory(upload_folder, safe_filename)
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=1800'  # 30 minutes
        
        # Log successful access
        log.info(action="notice_file_served", trace_info=client_info["ip_address"], message=f"Notice file served: {safe_filename}", secure=False)
        
        return response, 200
        
    except Exception as e:
        log.critical(action="notice_serving_error", trace_info=client_info["ip_address"], message=f"Error serving notice file {filename}: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return jsonify(response), status

@api.route('/uploads/exam_results/<path:filename>')
@handle_async_errors
async def exam_results_file(filename: str) -> Tuple[Response, int]:
    """Serve exam result files with enhanced security"""
    # Get client info for logging
    client_info = await get_client_info() or {}
    
    # Get upload folder from config
    upload_folder = config.EXAM_RESULTS_UPLOAD_FOLDER
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_exam_result_request", trace_info=client_info["ip_address"], message=f"Invalid filename: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="exam_result_file_not_found", trace_info=client_info["ip_address"], message=f"Exam result file not found: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    try:
        # Serve file with security headers
        response = await send_from_directory(upload_folder, safe_filename)
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=3600'  # 1 hour
        
        # Log successful access
        log.info(action="exam_result_file_served", trace_info=client_info["ip_address"], message=f"Exam result file served: {safe_filename}", secure=False)
        
        return response, 200
        
    except Exception as e:
        log.critical(action="exam_result_serving_error", trace_info=client_info["ip_address"], message=f"Error serving exam result file {filename}: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return jsonify(response), status

@api.route('/uploads/gallery/<gender>/<folder>/<path:filename>')
@handle_async_errors
async def gallery_file(gender: str, folder: str, filename: str) -> Tuple[Response, int]:
    """Serve gallery files with enhanced security and validation"""
    # Get client info for logging
    client_info = await get_client_info() or {}
    
    # Validate gender parameter
    if gender not in config.ALLOWED_GALLERY_GENDERS:
        log.warning(action="invalid_gallery_gender", trace_info=client_info["ip_address"], message=f"Invalid gender parameter: {gender}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['invalid_gender'], 400)
        return jsonify(response), status
    
    # Validate folder parameter
    if not validate_folder_access(folder, config.ALLOWED_GALLERY_FOLDERS):
        log.warning(action="invalid_gallery_folder", trace_info=client_info["ip_address"], message=f"Invalid folder parameter: {folder}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['invalid_folder'], 400)
        return jsonify(response), status
    
    # Get upload folder path
    upload_folder = os.path.join(
        current_app.config['BASE_UPLOAD_FOLDER'], 
        'gallery', gender, folder
    )
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_gallery_file_request", trace_info=client_info["ip_address"], message=f"Invalid filename: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="gallery_file_not_found", trace_info=client_info["ip_address"], message=f"Gallery file not found: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    try:
        # Serve file with security headers
        response = await send_from_directory(upload_folder, safe_filename)
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=7200'  # 2 hours
        
        # Log successful access
        log.info(action="gallery_file_served", trace_info=client_info["ip_address"], message=f"Gallery file served: {gender}/{folder}/{safe_filename}", secure=False)
        
        return response, 200
        
    except Exception as e:
        log.critical(action="gallery_serving_error", trace_info=client_info["ip_address"], message=f"Error serving gallery file {filename}: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return jsonify(response), status

@api.route('/uploads/gallery/classes/<folder>/<path:filename>')
@handle_async_errors
async def gallery_classes_file(folder: str, filename: str) -> Tuple[Response, int]:
    """Serve gallery class files with enhanced security and validation"""
    # Get client info for logging
    client_info = await get_client_info() or {}
    
    # Validate folder parameter
    if not validate_folder_access(folder, config.ALLOWED_CLASS_FOLDERS):
        log.warning(action="invalid_class_folder", trace_info=client_info["ip_address"], message=f"Invalid class folder parameter: {folder}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['invalid_folder'], 400)
        return jsonify(response), status
    
    # Get upload folder path
    upload_folder = os.path.join(
        current_app.config['BASE_UPLOAD_FOLDER'], 
        'gallery', 'classes', folder
    )
    
    # Sanitize and validate filename
    file_path, safe_filename = get_safe_file_path(upload_folder, filename)
    
    if not file_path or not safe_filename:
        log.warning(action="invalid_class_file_request", trace_info=client_info["ip_address"], message=f"Invalid filename: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    # Check if file exists
    if not os.path.isfile(file_path):
        log.warning(action="class_file_not_found", trace_info=client_info["ip_address"], message=f"Class file not found: {filename}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['file_not_found'], 404)
        return jsonify(response), status
    
    try:
        # Serve file with security headers
        response = await send_from_directory(upload_folder, safe_filename)
        
        # Add security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Cache-Control'] = 'public, max-age=7200'  # 2 hours
        
        # Log successful access
        log.info(action="class_file_served", trace_info=client_info["ip_address"], message=f"Class file served: {folder}/{safe_filename}", secure=False)
        
        return response, 200
        
    except Exception as e:
        log.critical(action="class_file_serving_error", trace_info=client_info["ip_address"], message=f"Error serving class file {filename}: {str(e)}", secure=False)
        response, status = send_json_response(ERROR_MESSAGES['internal_error'], 500)
        return jsonify(response), status
