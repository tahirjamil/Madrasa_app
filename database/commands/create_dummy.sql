-- Insert into users table
INSERT INTO users (
    id, fullname, phone, password, email, ip_address
) VALUES (
    9999, 'dummy', '+8801000000000', 'Dummy@123', 'gmail@example.com', '192.0.0.8'
);

-- Insert into people table
INSERT INTO people (
    id, user_id, member_id, student_id, name_en, name_bn, name_ar, date_of_birth, birth_certificate, national_id, 
    blood_group, gender, title1, present_address, address_en, address_bn, address_ar, permanent_address, father_or_spouse, father_en, 
    father_bn, father_ar, mother_en, mother_bn, mother_ar, class, phone, guardian_number, degree, image_path
) VALUES (
    9999, 9999, 'M9999', 'S9999', 'Dummy Name', 'ডামি নাম', 'اسم وهمي', '2000-01-01', '1234567890', '9876543210', 
    'O+', 'Male', 'Mawlana.', '123 Dummy Street', '123 Dummy Street', '১২৩ ডামি স্ট্রিট', '١٢٣ شارع وهمي', '456 Fake Avenue', 'Father Dummy', 'Father Dummy', 
    'ফাদার ডামি', 'أب وهمي', 'Mother Dummy', 'মাদার ডামি', 'أم وهمية', 'Daora', '+8801000000000', '+8801999999999', 'Mawlana', 'user_profile_img/dummy.webp'
);

-- Insert into transactions table (donation)
INSERT INTO transactions (
    id, type, month, amount, date
) VALUES (
    9999, 'donation', 9, 9999, '2009-09-09'
);

-- Insert into transactions table (generic transaction)
INSERT INTO transactions (
    id, type, amount, date
) VALUES (
    9999, 'transaction', 9999, '2009-09-09'
);

-- Insert into payment table
INSERT INTO payment (
    id, food, special_food, due_months
) VALUES (
    9999, 1, 1, 9
);
