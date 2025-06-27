from flask import current_app, session, redirect, url_for, render_template, flash, request
import pymysql
import pymysql.cursors
from database import connect_to_db
from logger import log_event
from . import admin_routes
from werkzeug.utils import secure_filename
import os

@admin_routes.route('/members', methods=['GET', 'POST'])
def members():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            # Fetch all people and pending verifies
            cursor.execute("SELECT * FROM people")
            people = cursor.fetchall()
            cursor.execute("SELECT * FROM verify_people")
            pending = cursor.fetchall()
    finally:
        conn.close()

    # Build list of distinct account types
    types = sorted({m['acc_type'] for m in people if m.get('acc_type')})
    selected_type = request.args.get('type', types[0] if types else None)
    members = [m for m in people if m['acc_type'] == selected_type] if selected_type else []

    return render_template("admin/members.html",
                           types=types,
                           selected_type=selected_type,
                           members=members,
                           pending=pending)


@admin_routes.route('/members/verify_people/<int:verify_people_id>', methods=['POST'])
def verify_member(verify_people_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            # Fetch pending user
            cursor.execute("SELECT * FROM verify_people WHERE id = %s", (verify_people_id,))
            row = cursor.fetchone()
            if not row:
                flash("No pending user found.", "warning")
                return redirect(url_for('admin_routes.members'))

            # Prepare insert into people
            cols = ', '.join(row.keys())
            placeholders = ', '.join(['%s'] * len(row))
            sql = f"INSERT INTO people ({cols}) VALUES ({placeholders})"
            cursor.execute(sql, tuple(row.values()))

            # Remove from verify_people table
            cursor.execute("DELETE FROM verify_people WHERE id = %s", (verify_people_id,))
            conn.commit()

            flash("Member verified successfully.", "success")
            log_event("member_verified", session.get('admin_username', 'admin'), f"ID {verify_people_id}")
    except Exception as e:
        conn.rollback()
        flash(f"Error verifying member: {e}", "danger")
        log_event("verify_people_error", session.get('admin_username', 'admin'), str(e))
    finally:
        conn.close()

    return redirect(url_for('admin_routes.members'))

@admin_routes.route('/add_member', methods=['GET','POST'])
def add_member():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    genders = ['Male','Female']
    blood_groups = ['A+','A-','B+','B-','AB+','AB-','O+','O-']
    types = ['admins','students','teachers','staffs','donors','badri_members','others']

    if request.method == 'POST':
        fields = ["name_en","name_bn","name_ar","member_id","student_id","phone",
                  "date_of_birth","national_id","blood_group","degree","gender",
                  "title1","source","present_address","address_bn","address_ar",
                  "permanent_address","father_or_spouse","mail","father_en",
                  "father_bn","father_ar","mother_en","mother_bn","mother_ar",
                  "acc_type"]
        data = {f: request.form.get(f) for f in fields if request.form.get(f)}

        # Handle image upload
        image = request.files.get('image')
        if image and image.filename:
            filename = secure_filename(image.filename)
            upload_path = os.path.join(current_app.config['IMG_UPLOAD_FOLDER'], filename)
            image.save(upload_path)
            data['image_path'] = upload_path  # or just filename if you store relative path

        conn = connect_to_db()
        try:
            with conn.cursor() as cursor:
                cols = ','.join(data.keys())
                vals = ','.join(['%s']*len(data))
                cursor.execute(
                  f"INSERT INTO people ({cols}) VALUES ({vals})",
                  tuple(data.values())
                )
                conn.commit()
            flash("Member added successfully","success")
            return redirect(url_for('admin_routes.members'))
        finally:
            conn.close()

    return render_template('admin/add_member.html',
                           genders=genders,
                           types=types,
                           blood_groups=blood_groups)