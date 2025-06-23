from flask import render_template, request, redirect, url_for, session, flash
import pymysql
import pymysql.cursors
from . import admin_routes
from database import connect_to_db
import os
from logger import log_event
from helpers_admin import backup_table

@admin_routes.route('/')
def admin_dashboard():
    conn = connect_to_db()
    databases = []
    tables = {}
    selected_db = request.args.get('db', 'madrasadb')

    try:
        with conn.cursor(cursor=pymysql.cursors.Cursor) as cursor:
            cursor.execute("SHOW DATABASES")
            databases = [row[0] for row in cursor.fetchall()]

            if selected_db not in databases:
                selected_db = databases[0] if databases else None

            if selected_db:
                cursor.execute(f"USE {selected_db}")
                cursor.execute("SHOW TABLES")
                table_list = [row[0] for row in cursor.fetchall()]

                for table in table_list:
                    cursor.execute(f"DESCRIBE {table}")
                    tables[table] = cursor.fetchall()
    except Exception as e:
        flash(f"Dashboard error: {e}", "danger")
    finally:
        conn.close()

    return render_template("admin/dashboard.html", databases=databases, tables=tables, selected_db=selected_db)


@admin_routes.route('/drop', methods=['POST'])
def drop_object():
    object_type = request.form.get('type')
    name = request.form.get('name')
    db = request.form.get('db')
    password = request.form.get('password')
    ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

    if password != ADMIN_PASS:
        flash("Incorrect admin password.", "danger")
        return redirect(url_for('admin_routes.admin_dashboard', db=db))

    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            
            if object_type == "table":
                success, msg = backup_table(db, name)
                if success:
                    flash(f"✅ Backup saved: {msg}", "info")
                    log_event("backup_table", name, msg)

                    cursor.execute(f"USE {db}")
                    cursor.execute(f"DROP TABLE `{name}`")
                    flash(f"Table '{name}' dropped successfully.", "success")
                    log_event("drop_table", name, f"From DB: {db}")

                else:
                    flash(f"⚠️ Backup failed: {msg}", "warning")
                    flash(f"Please Use root user to Drop")
                    log_event("backup_error", name, msg)


            elif object_type == "database":
                flash(f"Database can be dropped only by root user.", "success")
                log_event("drop_database", name, "tried to delete full DB")
            conn.commit()
    except Exception as e:
        flash(f"Drop error: {e}", "danger")
        log_event("drop_error", name, str(e))
    finally:
        conn.close()

    return redirect(url_for('admin_routes.admin_dashboard'))


@admin_routes.route('/create', methods=['POST'])
def create_object():
    command = request.form.get('command')
    password = request.form.get('password')
    ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

    if password != ADMIN_PASS:
        flash("Incorrect admin password.", "danger")
        return redirect(url_for('admin_routes.admin_dashboard'))

    if not command or not command.strip().lower().startswith("create"):
        flash("Only CREATE commands are allowed.", "danger")
        return redirect(url_for('admin_routes.admin_dashboard'))

    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(command)
            conn.commit()
            flash("Command executed successfully.", "success")
            log_event("create_command", "admin", command)
    except Exception as e:
        flash(f"MySQL error: {str(e)}", "danger")
        log_event("create_error", "admin", str(e))
    finally:
        conn.close()

    return redirect(url_for('admin_routes.admin_dashboard'))
@admin_routes.route('/members')
def members():
    return render_template("admin/members.html")

@admin_routes.route('/routine')
def routine():
    return render_template("admin/routine.html")

@admin_routes.route('/notice')
def notice():
    return render_template("admin/notice.html")

@admin_routes.route('/events')
def events():
    return render_template("admin/events.html")

@admin_routes.route('/exam_results')
def exam_results():
    return render_template("admin/exam_results.html")

@admin_routes.route('/madrasha_pictures')
def madrasha_pictures():
    return render_template("admin/madrasha_pictures.html")

@admin_routes.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin_routes.login'))
