from flask import render_template
from .auth import login_required

@login_required
def dashboard():
    return render_template('admin/dashboard.html')

@login_required
def members():
    return render_template('admin/members.html')

@login_required
def notice():
    return render_template('admin/notice.html')

@login_required
def routine():
    return render_template('admin/routine.html')

@login_required
def events():
    return render_template('admin/events.html')

@login_required
def exam_results():
    return render_template('admin/exam_results.html')

@login_required
def madrasha_pictures():
    return render_template('admin/madrasha_pictures.html')
