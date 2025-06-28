from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, DateField, SubmitField
from wtforms.validators import DataRequired

class AddMemberForm(FlaskForm):
    name_en = StringField('Name (English)', validators=[DataRequired()])
    name_bn = StringField('Name (Bangla)')
    name_ar = StringField('Name (Arabic)')
    member_id = StringField('Member ID')
    student_id = StringField('Student ID')
    phone = StringField('Phone', validators=[DataRequired()])
    date_of_birth = DateField('Date of Birth', format='%Y-%m-%d')
    national_id = StringField('National ID')
    blood_group = SelectField('Blood Group', choices=[
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-')
    ])
    degree = StringField('Degree')
    gender = SelectField('Gender', choices=[('Male', 'Male'), ('Female', 'Female')])
    acc_type = SelectField('Account Type', choices=[
        ('admins', 'Admins'), ('students', 'Students'),
        ('teachers', 'Teachers'), ('staffs', 'Staffs'),
        ('donors', 'Donors'), ('badri_members', 'Badri Members'),
        ('others', 'Others')
    ])
    image = FileField('Image')
    submit = SubmitField('Add Member')
