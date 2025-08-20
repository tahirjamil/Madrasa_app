import re
from fastapi import Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import config
from utils.helpers.fastapi_helpers import handle_async_errors, templates
from utils.helpers.helpers import rate_limit
import os
import markdown
from datetime import datetime
from routes.web_routes import web_routes, url_for
from utils.helpers.improved_functions import get_env_var

@web_routes.get("/", response_class=HTMLResponse, name="home")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {
        "request": request,
        "current_year": datetime.now().year,
    })

@web_routes.get("/donate", response_class=HTMLResponse, name="donate")
async def donate(request: Request):
    return templates.TemplateResponse("donate.html", {
        "request": request,
        "current_year": datetime.now().year,
    })

@web_routes.get('/privacy', response_class=HTMLResponse, name="privacy")
@handle_async_errors
async def privacy():
    # Load contact info from environment variables
    contact_email = get_env_var('BUSINESS_EMAIL', '')
    contact_phone = get_env_var('BUSINESS_PHONE', '')
    effective_date = get_env_var('PRIVACY_POLICY_EFFECTIVE_DATE', '')

    try:
        # Use safe path join
        policy_path = os.path.join(config.get_project_root(), 'content', 'privacy_policy.md')
        with open(policy_path, 'r', encoding='utf-8') as f:
            policy_md = f.read()
    except FileNotFoundError:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="privacy_policy_file_not_found", trace_info="system", message=f"Privacy policy file not found", secure=False)
        return templates.TemplateResponse(
        'error.html',
        {
            "error_title": "Privacy Policy Unavailable",
            "error_message": "The privacy policy is currently unavailable. Please try again later or contact support.",
            "contact_email": contact_email
        }, 503)
    except Exception as e:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="privacy_policy_file_error", trace_info="system", message=f"Error reading privacy policy file: {type(e).__name__}", secure=False)
        return templates.TemplateResponse(
        'error.html',
        {
            "error_title": "Privacy Policy Error",
            "error_message": "There was an error loading the privacy policy. Please try again later or contact support.",
            "contact_email": contact_email
        }, 500)

    # Replace placeholders with actual contact info
    policy_md = policy_md.replace('{{ contact_email }}', contact_email)
    policy_md = policy_md.replace('{{ phone }}', contact_phone)

    # Split content into sections based on '## ' headings
    sections_md = re.split(r'\n## ', policy_md.strip())

    # The first element is the introduction
    introduction_md = sections_md.pop(0) if sections_md else ""
    introduction_html = markdown.markdown(introduction_md, extensions=['extra'])

    # The rest are the collapsible sections
    parsed_sections = []
    for section_md in sections_md:
        if not section_md.strip():
            continue
        
        lines = section_md.strip().split('\n', 1)
        title = lines[0].strip()
        content_md = lines[1] if len(lines) > 1 else ''
        
        parsed_sections.append({
            'title': title,
            'content_html': markdown.markdown(content_md, extensions=['extra']),
            'id': re.sub(r'[^a-zA-Z0-9]', '', title.split('.')[0])
        })

    return templates.TemplateResponse(
        'privacy.html',
        {
            "introduction_html": introduction_html,
            "sections": parsed_sections,
            "effective_date": effective_date
        })

@web_routes.get('/terms', response_class=HTMLResponse, name="terms")
@handle_async_errors
async def terms(request: Request):
    from utils.helpers.logger import log
    contact_email = get_env_var('BUSINESS_EMAIL', '')
    effective_date = get_env_var('TERMS_EFFECTIVE_DATE', '')
    
    try:
        # Use safe path join
        terms_path = os.path.join(config.get_project_root(), 'content', 'terms.md')
        with open(terms_path, 'r', encoding='utf-8') as f:
            terms_md = f.read()
    except FileNotFoundError:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="terms_file_not_found", trace_info="system", message=f"Terms file not found", secure=False)
        return templates.TemplateResponse(
        'error.html',
        {
            "error_title": "Terms of Service Unavailable",
            "error_message": "The terms of service are currently unavailable. Please try again later or contact support.",
            "contact_email": contact_email
        }, 503)
    except Exception as e:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="terms_file_error", trace_info="system", message=f"Error reading terms file: {type(e).__name__}", secure=False)
        return templates.TemplateResponse(
        'error.html',
        {
            "error_title": "Terms of Service Error",
            "error_message": "There was an error loading the terms of service. Please try again later or contact support.",
            "contact_email": contact_email
        }, 500)
    
     # Replace placeholders with actual contact info
    terms_md = terms_md.replace('{{ contact_email }}', contact_email)

    # Split content into sections based on '## ' headings
    sections_md = re.split(r'\n## ', terms_md.strip())
    
    # The first element is the introduction
    introduction_md = sections_md.pop(0) if sections_md else ""
    introduction_html = markdown.markdown(introduction_md, extensions=['extra'])

    parsed_sections = []
    for section_md in sections_md:
        if not section_md.strip():
            continue
        
        lines = section_md.strip().split('\n', 1)
        title = lines[0].strip()
        content_md = lines[1] if len(lines) > 1 else ''
        
        parsed_sections.append({
            'title': title,
            'content_html': markdown.markdown(content_md, extensions=['extra']),
            'id': re.sub(r'[^a-zA-Z0-9]', '', title.split('.')[0])
        })
    
    return templates.TemplateResponse(
        'terms.html',
        {
            "introduction_html": introduction_html,
            "sections": parsed_sections,
            "effective_date": effective_date
        })

# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------------------------------------------

# TODO: Add account Management routes


# TODO: Uncomment and implement info routes if needed
# @web_routes.get('/info', response_class=HTMLResponse, name="info")
# @handle_async_errors
# @rate_limit(max_requests=500, window=60)
# async def info_admin(request: Request):

#     # Thread-safe access to request log
#     if config.is_testing():
#         logs = []
#     else:
#         request_log = request.app.state.request_response_log
#         request_log_lock = request.app.state.request_log_lock
#         with request_log_lock:
#             logs = list(request_log)[-100:]

#     return templates.TemplateResponse("admin/info.html", {"request": request, "logs": logs})

# @web_routes.get('/info/data', name="info_data")
# @handle_async_errors
# async def info_data_admin(request: Request):

#     if config.is_testing():
#         return JSONResponse(content=[])
#     # Thread-safe access to request log
#     request_log = request.app.state.request_response_log
#     request_log_lock = request.app.state.request_log_lock
#     with request_log_lock:
#         logs = list(request_log)[-100:]
#     # serializable copy
#     out = []
#     for e in logs:
#         out.append({
#             "time":     e["time"],
#             "ip":       e["ip"],
#             "method":   e["method"],
#             "path":     e["path"],
#             "req_json": e.get("req_json"),
#             "res_json": e.get("res_json")
#         })
#     return JSONResponse(content=out)
