from typing import Optional
from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr

from utils.helpers.improved_functions import get_env_var, send_json_response
from utils.helpers.fastapi_helpers import rate_limit, handle_async_errors
from . import web_routes, templates
from utils.helpers.helpers import send_email
import os
import markdown
import re
from datetime import datetime
import html  # For escaping HTML

# Pydantic models for form data
class ContactForm(BaseModel):
    fullname: str
    email_or_phone: str
    description: str

@web_routes.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request):
    from . import url_for
    return templates.TemplateResponse("home.html", {
        "request": request,
        "current_year": datetime.now().year,
        "url_for": url_for
    })

@web_routes.get("/donate", response_class=HTMLResponse, name="donate")
async def donate(request: Request):
    from . import url_for
    return templates.TemplateResponse("donate.html", {
        "request": request,
        "current_year": datetime.now().year,
        "url_for": url_for
    })

@web_routes.get('/contact', response_class=HTMLResponse, name="contact")
@handle_async_errors
@rate_limit(max_requests=50, window=60)  # 50 requests per minute to prevent spam
async def contact_get(request: Request):
    # Read raw comma‑separated strings from env
    raw_phones = get_env_var('BUSINESS_PHONE') or ''
    raw_emails = get_env_var('BUSINESS_EMAIL') or ''

    # Turn into clean lists
    phones = [p.strip() for p in raw_phones.split(',') if p.strip()] if raw_phones else []
    emails = [e.strip() for e in raw_emails.split(',') if e.strip()] if raw_emails else []
    
    from . import url_for
    return templates.TemplateResponse("contact.html", {
        "request": request,
        "current_year": datetime.now().year,
        "business_phones": phones,
        "business_emails": emails,
        "business_email": emails[0] if emails else '',
        "business_phone": phones[0] if phones else '',
        "url_for": url_for
    })

@web_routes.post('/contact')
@handle_async_errors
@rate_limit(max_requests=50, window=60)
async def contact_post(
    request: Request,
    fullname: str = Form(...),
    email_or_phone: str = Form(...),
    description: str = Form(...)
):
    # Read raw comma‑separated strings from env
    raw_phones = get_env_var('BUSINESS_PHONE') or ''
    raw_emails = get_env_var('BUSINESS_EMAIL') or ''

    # Turn into clean lists
    phones = [p.strip() for p in raw_phones.split(',') if p.strip()] if raw_phones else []
    emails = [e.strip() for e in raw_emails.split(',') if e.strip()] if raw_emails else []

    # Validate required fields
    error_message = None
    if not fullname or not email_or_phone or not description:
        error_message = 'All fields are required.'
    
    # Validate field lengths
    elif len(fullname) > 100 or len(email_or_phone) > 100 or len(description) > 1000:
        error_message = 'Please keep your input within reasonable length limits.'
    
    # Basic email/phone validation
    if '@' not in email_or_phone and not re.match(r'^[\d\s\+\-\(\)]+$', email_or_phone):
        error_message = 'Please provide a valid email address or phone number.'

    if error_message:
        return RedirectResponse(url=str(request.url) + "?error=true", status_code=303) # Use 303 for redirect

    try:
        # Escape HTML to prevent XSS
        safe_fullname = html.escape(fullname)
        safe_contact = html.escape(email_or_phone)
        safe_description = html.escape(description)
        
        await send_email(
            to_email=emails[0],  # primary admin address
            subject="Contact Form Submission",
            body=f"Name: {safe_fullname}\nContact: {safe_contact}\n\nDescription: {safe_description}"
        )
    except Exception as e:
        # Log the error but don't expose details to user
        from utils.helpers.logger import log
        log.error(action="contact_form_error", trace_info="web", message=str(e), secure=False)
        # Flash message is not directly available in FastAPI, so we'll redirect with a query parameter
        return RedirectResponse(url=str(request.url) + "?error=true", status_code=303)

    return RedirectResponse(url=str(request.url) + "?success=true", status_code=303)

@web_routes.get('/privacy', response_class=HTMLResponse, name="privacy")
@handle_async_errors
async def privacy(request: Request):
    from utils.helpers.logger import log
    
    # Debug: Log the request
    log.info(action="privacy_page_accessed", trace_info=request.client.host if request.client else "unknown",
             message="Privacy page accessed", secure=False)
    
    # Construct the full path to the markdown file with debugging
    current_file = __file__
    log.info(action="privacy_debug", trace_info="web", message=f"Current file: {current_file}", secure=False)
    
    content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'content')
    log.info(action="privacy_debug", trace_info="web", message=f"Content directory: {content_dir}", secure=False)
    
    md_path = os.path.join(content_dir, 'privacy_policy.md')
    log.info(action="privacy_debug", trace_info="web", message=f"Looking for privacy policy at: {md_path}", secure=False)
    
    # Check if file exists
    file_exists = os.path.exists(md_path)
    log.info(action="privacy_debug", trace_info="web", message=f"File exists: {file_exists}", secure=False)
    
    # Default content in case file doesn't exist
    title = "Privacy Policy"
    content = "<p>Privacy policy content is not available at the moment.</p>"
    last_updated = "Not available"
    
    try:
        # Read and parse the markdown file
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            
        # Extract title if it's in the first line as # Title
        lines = md_content.split('\n')
        if lines and lines[0].startswith('# '):
            title = lines[0][2:].strip()
            md_content = '\n'.join(lines[1:])
        
        # Convert markdown to HTML
        content = markdown.markdown(md_content, extensions=['extra', 'nl2br'])
        
        # Get last modified date
        last_modified = os.path.getmtime(md_path)
        last_updated = datetime.fromtimestamp(last_modified).strftime('%B %d, %Y')
        
    except FileNotFoundError as e:
        # Log the error with more details
        log.warning(action="privacy_policy_not_found", trace_info="web", 
                    message=f"Privacy policy file not found at {md_path}. Error: {str(e)}", secure=False)
        # List files in content directory for debugging
        try:
            if os.path.exists(content_dir):
                files = os.listdir(content_dir)
                log.info(action="privacy_debug", trace_info="web", 
                         message=f"Files in content directory: {files}", secure=False)
            else:
                log.error(action="privacy_debug", trace_info="web", 
                          message=f"Content directory does not exist: {content_dir}", secure=False)
        except Exception as list_error:
            log.error(action="privacy_debug", trace_info="web", 
                      message=f"Error listing content directory: {str(list_error)}", secure=False)
    except Exception as e:
        # Log any other errors with full traceback
        import traceback
        log.error(action="privacy_policy_error", trace_info="web", 
                  message=f"Error loading privacy policy: {str(e)}\nTraceback: {traceback.format_exc()}", secure=False)
    
    from . import url_for
    return templates.TemplateResponse('privacy.html', {
        "request": request,
        "title": title,
        "content": content,
        "last_updated": last_updated,
        "current_year": datetime.now().year,
        "url_for": url_for
    })

@web_routes.get('/terms', response_class=HTMLResponse, name="terms")
@handle_async_errors
async def terms(request: Request):
    from utils.helpers.logger import log
    
    # Debug: Log the request
    log.info(action="terms_page_accessed", trace_info=request.client.host if request.client else "unknown",
             message="Terms page accessed", secure=False)
    
    # Construct the full path to the markdown file with debugging
    current_file = __file__
    log.info(action="terms_debug", trace_info="web", message=f"Current file: {current_file}", secure=False)
    
    content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'content')
    log.info(action="terms_debug", trace_info="web", message=f"Content directory: {content_dir}", secure=False)
    
    md_path = os.path.join(content_dir, 'terms.md')
    log.info(action="terms_debug", trace_info="web", message=f"Looking for terms at: {md_path}", secure=False)
    
    # Check if file exists
    file_exists = os.path.exists(md_path)
    log.info(action="terms_debug", trace_info="web", message=f"File exists: {file_exists}", secure=False)
    
    # Default content in case file doesn't exist
    title = "Terms of Service"
    content = "<p>Terms of service content is not available at the moment.</p>"
    last_updated = "Not available"
    
    try:
        # Read and parse the markdown file
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            
        # Extract title if it's in the first line as # Title
        lines = md_content.split('\n')
        if lines and lines[0].startswith('# '):
            title = lines[0][2:].strip()
            md_content = '\n'.join(lines[1:])
        
        # Convert markdown to HTML
        content = markdown.markdown(md_content, extensions=['extra', 'nl2br'])
        
        # Get last modified date
        last_modified = os.path.getmtime(md_path)
        last_updated = datetime.fromtimestamp(last_modified).strftime('%B %d, %Y')
        
    except FileNotFoundError as e:
        # Log the error with more details
        log.warning(action="terms_not_found", trace_info="web", 
                    message=f"Terms file not found at {md_path}. Error: {str(e)}", secure=False)
        # List files in content directory for debugging
        try:
            if os.path.exists(content_dir):
                files = os.listdir(content_dir)
                log.info(action="terms_debug", trace_info="web", 
                         message=f"Files in content directory: {files}", secure=False)
            else:
                log.error(action="terms_debug", trace_info="web", 
                          message=f"Content directory does not exist: {content_dir}", secure=False)
        except Exception as list_error:
            log.error(action="terms_debug", trace_info="web", 
                      message=f"Error listing content directory: {str(list_error)}", secure=False)
    except Exception as e:
        # Log any other errors with full traceback
        import traceback
        log.error(action="terms_error", trace_info="web", 
                  message=f"Error loading terms: {str(e)}\nTraceback: {traceback.format_exc()}", secure=False)
    
    from . import url_for
    return templates.TemplateResponse('terms.html', {
        "request": request,
        "title": title,
        "content": content,
        "last_updated": last_updated,
        "current_year": datetime.now().year,
        "url_for": url_for
    })

@web_routes.get("/debug-paths")
async def debug_paths(request: Request):
    """Debug endpoint to check file paths"""
    import os
    from utils.helpers.logger import log
    
    current_file = __file__
    content_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'content')
    
    privacy_path = os.path.join(content_dir, 'privacy_policy.md')
    terms_path = os.path.join(content_dir, 'terms.md')
    
    result = {
        "current_file": current_file,
        "content_dir": content_dir,
        "content_dir_exists": os.path.exists(content_dir),
        "privacy_policy_path": privacy_path,
        "privacy_policy_exists": os.path.exists(privacy_path),
        "terms_path": terms_path,
        "terms_exists": os.path.exists(terms_path),
    }
    
    # List files in content directory if it exists
    if os.path.exists(content_dir):
        try:
            result["content_files"] = os.listdir(content_dir)
        except Exception as e:
            result["content_files_error"] = str(e)
    
    log.info(action="debug_paths", trace_info="debug", message=f"Path debug info: {result}", secure=False)
    
    return result

@web_routes.get("/account/{page_type}", response_class=HTMLResponse)
async def manage_account(request: Request, page_type: str):
    """Manage account (deactivate/delete) with enhanced security"""
    # Validate page type
    if page_type not in ("remove", "deactivate"):
        raise HTTPException(status_code=400, detail="Invalid page type")
    
    return templates.TemplateResponse(
        "account_manage.html",
        {
            "request": request,
            "page_type": page_type.capitalize()
        }
    )