from flask import render_template, request, flash, session, redirect, url_for
import pymysql
import pymysql.cursors
from . import admin_routes
from database import connect_to_db
import os
from logger import log_event


@admin_routes.route('/', methods=['GET', 'POST'])
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_routes.login'))

    conn = connect_to_db()
    databases = []
    tables = {}
    selected_db = request.args.get('db', 'madrasadb')
    query_result = None
    query_error = None

    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SHOW DATABASES")
            databases = [row["Database"] for row in cursor.fetchall()]

            if selected_db not in databases:
                selected_db = databases[0] if databases else None

            if selected_db:
                cursor.execute(f"USE {selected_db}")
                cursor.execute("SHOW TABLES")
                table_list = [row[f'Tables_in_{selected_db}'] for row in cursor.fetchall()]
                for table in table_list:
                    cursor.execute(f"DESCRIBE {table}")
                    tables[table] = cursor.fetchall()

            if request.method == "POST":
                username = request.form.get('username')
                password = request.form.get('password')
                raw_sql = request.form.get('sql', '')

                ADMIN_USER = os.getenv("ADMIN_USERNAME")
                ADMIN_PASS = os.getenv("ADMIN_PASSWORD")

                if username != ADMIN_USER or password != ADMIN_PASS:
                    flash("Unauthorized admin login.", "danger")
                else:
                    forbidden = ['drop', 'truncate', 'alter', 'rename', 'create database', 'use']
                    if any(word in raw_sql.lower() for word in forbidden):
                        flash("🚫 Dangerous queries are not allowed (DROP, ALTER, etc).", "danger")
                        log_event("forbidden_query_attempt", username, raw_sql)
                    else:
                        try:
                            cursor.execute(raw_sql)
                            if cursor.description:  # SELECT-like
                                query_result = cursor.fetchall()
                            else:
                                conn.commit()
                                query_result = f"✅ Query OK. Rows affected: {cursor.rowcount}"
                            log_event("query_run", username, raw_sql)
                        except Exception as e:
                            query_error = str(e)
                            log_event("query_error", username, f"{raw_sql} | {str(e)}")
    except Exception as e:
        query_error = str(e)
    finally:
        conn.close()

    return render_template("admin/dashboard.html",
                           databases=databases,
                           tables=tables,
                           selected_db=selected_db,
                           query_result=query_result,
                           query_error=query_error)

@admin_routes.route('/routine')
def routine():
    return render_template("admin/routine.html")

@admin_routes.route('/events')
def events():
    return render_template("admin/events.html")

@admin_routes.route('/madrasha_pictures')
def madrasha_pictures():
    return render_template("admin/madrasha_pictures.html")