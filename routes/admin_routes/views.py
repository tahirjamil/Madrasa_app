from flask import render_template, redirect, url_for, session
from . import admin_routes

@admin_routes.route('/')
def admin_dashboard():
    return render_template("admin/dashboard.html")

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
