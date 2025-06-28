from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FileField, SubmitField, DateField
from wtforms.validators import DataRequired

class AddMemberForm(FlaskForm):
    name_en = StringField('Name (EN)', validators=[DataRequired()])
    phone = StringField('Phone', validators=[DataRequired()])
    father_en = StringField('Father Name (EN)')
    father_bn = StringField('Father Name (BN)')
    father_ar = StringField('Father Name (AR)')
    mother_en = StringField('Mother Name (EN)')
    mother_bn = StringField('Mother Name (BN)')
    mother_ar = StringField('Mother Name (AR)')
    acc_type = SelectField('Account Type*', choices=[], validators=[DataRequired()])
    image = FileField('Upload Image')
    submit = SubmitField('Submit')
