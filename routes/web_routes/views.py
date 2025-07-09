from . import web_routes
from flask import render_template, request, redirect, url_for, flash, current_app
from helpers import send_email
import os

@web_routes.route('/contact', methods=['GET', 'POST'])
def contact():
    # Contact info from environment/config
    contact_phone = os.getenv('MADRASA_PHONE', "")
    contact_email = os.getenv('EMAIL_ADDRESS', "")

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        email_or_phone = request.form.get('email_or_phone', '').strip()
        description = request.form.get('description', '').strip()

        # Basic validation
        if not fullname or not email_or_phone or not description:
            flash('All fields are required.', 'danger')
            return redirect(url_for('web_routes.contact'))

        # Send email notification
        try:
            send_email(
                to_email=contact_email,
                subject="Contact Form Submission",
                body=f"""Name: {fullname}
                Contact: {email_or_phone}

                Description: {description}"""
                )
        except Exception as e:
            flash(f'An error occurred while sending your message: {str(e)}', 'danger')
            return redirect(url_for('web_routes.contact'))

        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('web_routes.contact'))

    # Render contact page for GET
    return render_template('contact.html', phones=contact_phone, emails=contact_email)

@web_routes.route('/privacy')
def privacy():
    return render_template(
        'privacy.html',
        effective_date='July 9, 2025',
        contact_email=os.getenv('EMAIL_ADDRESS', ""))