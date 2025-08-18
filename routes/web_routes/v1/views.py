from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse

from utils.helpers.fastapi_helpers import handle_async_errors
from . import web_routes, templates
import os
import markdown
from datetime import datetime

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