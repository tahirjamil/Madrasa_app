from typing import Tuple
from utils.helpers.improved_functions import get_env_var, send_json_response
from . import web_routes
from quart import Response, jsonify, render_template, request, redirect, url_for, flash
from quart_babel import gettext as _
from utils.helpers.helpers import send_email, rate_limit, handle_async_errors
import os
import markdown
import re
from datetime import datetime
from quart_babel import gettext as _
import html  # For escaping HTML

@web_routes.route("/")
async def home():
    return await render_template("home.html", current_year=datetime.now().year)

@web_routes.route("/donate")
async def donate():
    return await render_template("donate.html", current_year=datetime.now().year)

@web_routes.route('/contact', methods=['GET', 'POST'])
@handle_async_errors
@rate_limit(max_requests=50, window=60)  # 50 requests per minute to prevent spam
async def contact():
    # Read raw comma‑separated strings from env
    raw_phones = get_env_var('BUSINESS_PHONE')
    raw_emails = get_env_var('BUSINESS_EMAIL')

    # Turn into clean lists
    phones = [p.strip() for p in raw_phones.split(',') if p.strip()]
    emails = [e.strip() for e in raw_emails.split(',') if e.strip()]

    if request.method == 'POST':
        form = await request.form
        fullname       = form.get('fullname', '').strip()
        email_or_phone = form.get('email_or_phone', '').strip()
        description    = form.get('description', '').strip()

        # Validate required fields
        if not fullname or not email_or_phone or not description:
            await flash('All fields are required.', 'danger')
            return redirect(url_for('web_routes.contact'))
        
        # Validate field lengths
        if len(fullname) > 100 or len(email_or_phone) > 100 or len(description) > 1000:
            await flash('Please keep your input within reasonable length limits.', 'danger')
            return redirect(url_for('web_routes.contact'))
        
        # Basic email/phone validation
        if '@' not in email_or_phone and not re.match(r'^[\d\s\+\-\(\)]+$', email_or_phone):
            await flash('Please provide a valid email address or phone number.', 'danger')
            return redirect(url_for('web_routes.contact'))

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
            await flash('An error occurred while sending your message. Please try again later.', 'danger')
            return redirect(url_for('web_routes.contact'))

        await flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('web_routes.contact'))

    # GET: render with lists
    return await render_template('contact.html', phones=phones, emails=emails)

@web_routes.route('/privacy')
@handle_async_errors
async def privacy():
    from config import config
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
        return await render_template('error.html', 
                                   error_title="Privacy Policy Unavailable",
                                   error_message="The privacy policy is currently unavailable. Please try again later or contact support.",
                                   contact_email=contact_email), 503
    except Exception as e:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="privacy_policy_file_error", trace_info="system", message=f"Error reading privacy policy file: {type(e).__name__}", secure=False)
        return await render_template('error.html', 
                                   error_title="Privacy Policy Error",
                                   error_message="There was an error loading the privacy policy. Please try again later or contact support.",
                                   contact_email=contact_email), 500

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
            'user_id': re.sub(r'[^a-zA-Z0-9]', '', title.split('.')[0])
        })

    return await render_template(
        'privacy.html',
        introduction_html=introduction_html,
        sections=parsed_sections,
        effective_date=effective_date
    )

@web_routes.route('/terms')
@handle_async_errors
async def terms():
    from config import config
    # Load contact info from environment variables
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
        return await render_template('error.html', 
                                   error_title="Terms of Service Unavailable",
                                   error_message="The terms of service are currently unavailable. Please try again later or contact support.",
                                   contact_email=contact_email), 503
    except Exception as e:
        # Log the error and return a user-friendly error page
        from utils.helpers.logger import log
        log.critical(action="terms_file_error", trace_info="system", message=f"Error reading terms file: {type(e).__name__}", secure=False)
        return await render_template('error.html', 
                                   error_title="Terms of Service Error",
                                   error_message="There was an error loading the terms of service. Please try again later or contact support.",
                                   contact_email=contact_email), 500

    # Replace placeholders with actual contact info
    terms_md = terms_md.replace('{{ contact_email }}', contact_email)

    # Split content into sections based on '## ' headings
    sections_md = re.split(r'\n## ', terms_md.strip())

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
            'user_id': re.sub(r'[^a-zA-Z0-9]', '', title.split('.')[0])
        })

    return await render_template(
        'terms.html',
        introduction_html=introduction_html,
        sections=parsed_sections,
        effective_date=effective_date
    )

@web_routes.route("/account/<page_type>", methods=['GET'])
async def manage_account(page_type: str):
    """Manage account (deactivate/delete) with enhanced security"""
    # Validate page type
    if page_type not in ("remove", "deactivate"):
        response, status = send_json_response(_("Invalid page type"), 400)
        return jsonify(response), status
    
    return await render_template(
        "account_manage.html",
        page_type=page_type.capitalize()
    )