from . import web_routes
from flask import render_template, request, redirect, url_for, flash, current_app
from helpers import send_email
import os

@web_routes.route('/contact', methods=['GET', 'POST'])
def contact():
    # Read raw comma‑separated strings from env
    raw_phones = os.getenv('MADRASA_PHONE', "")
    raw_emails = os.getenv('EMAIL_ADDRESS', "")

    # Turn into clean lists
    phones = [p.strip() for p in raw_phones.split(',') if p.strip()]
    emails = [e.strip() for e in raw_emails.split(',') if e.strip()]

    if request.method == 'POST':
        fullname       = request.form.get('fullname', '').strip()
        email_or_phone = request.form.get('email_or_phone', '').strip()
        description    = request.form.get('description', '').strip()

        if not fullname or not email_or_phone or not description:
            flash('All fields are required.', 'danger')
            return redirect(url_for('web_routes.contact'))

        try:
            send_email(
                to_email=emails[0],  # primary admin address
                subject="Contact Form Submission",
                body=f"Name: {fullname}\nContact: {email_or_phone}\n\nDescription: {description}"
            )
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('web_routes.contact'))

        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('web_routes.contact'))

    # GET: render with lists
    return render_template('contact.html', phones=phones, emails=emails)

@web_routes.route('/privacy')
def privacy():
    return render_template(
        'privacy.html',
        effective_date='July 9, 2025',
        contact_email=os.getenv('EMAIL_ADDRESS', ""))

@web_routes.route('/terms')
def terms():
    return render_template(
        'terms.html',
        effective_date='July 9, 2025'
        )