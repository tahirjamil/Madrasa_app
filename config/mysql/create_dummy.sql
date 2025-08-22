-- -- WARNING: This file contains dummy data for testing purposes only.
-- -- CRITICAL: This data MUST NOT be used in production environments.
-- -- The hardcoded password hash poses a security risk if left in production.
-- -- Ensure this dummy user is removed or disabled before deploying to production.

-- -- Insert into users table
-- INSERT INTO users (
--     user_id, fullname, phone, phone_hash, phone_encrypted, email, email_hash, email_encrypted, ip_address, password_hash
-- ) VALUES (
--     9999, 'Dummy', '+8801000000000', 
--     SHA2('+8801000000000', 256), -- phone_hash
--     'ENCRYPTED_PHONE_DUMMY', -- phone_encrypted (should be properly encrypted in production)
--     'dummy@gmail.com', 
--     SHA2('dummy@gmail.com', 256), -- email_hash
--     'ENCRYPTED_EMAIL_DUMMY', -- email_encrypted (should be properly encrypted in production)
--     '192.0.0.8', 
--     'scrypt:32768:8:1$wcVAqhqYEEVBrmCt$c6efe4945f8f54c807187650181abb5822402ecee2fe8744af128c0e1ca271a713bdcb4d501d142f57ad05b8fd97eaec6420afa26a94dcc48745744811719a51'
-- );

-- -- Insert into peoples table
-- INSERT INTO peoples (
--     person_id, user_id, serial, student_id, name, date_of_birth, 
--     birth_certificate, birth_certificate_encrypted, 
--     national_id, national_id_encrypted, 
--     blood_group, gender, title1, 
--     present_address, present_address_hash,
--     address, address_hash,
--     permanent_address, permanent_address_hash,
--     father_or_spouse, father_name, 
--     mother_name, class, phone, guardian_number, degree, image_path
-- ) VALUES (
--     9999, 9999, 9999, 9999, 'Dummy', '2000-01-01', 
--     '1234567890', 'ENCRYPTED_BC_DUMMY', -- birth_certificate_encrypted
--     '9876543210', 'ENCRYPTED_NID_DUMMY', -- national_id_encrypted
--     'O+', 'male', 'Mawlana.', 
--     '123 Dummy Street', SHA2('123 Dummy Street', 256), -- present_address_hash
--     '123 Dummy Street', SHA2('123 Dummy Street', 256), -- address_hash
--     '456 Fake Avenue', SHA2('456 Fake Avenue', 256), -- permanent_address_hash
--     'Father Dummy', 'Father Dummy', 
--     'Mother Dummy', 'Daora', '+8801000000000', '+8801999999999', 'Mawlana', 'user_profile_img/dummy.webp'
-- );

-- -- Insert into translations table
-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy', 'ডামি', 'اسم'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Address', 'ডামি ঠিকানা', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Father', 'ডামি পিতা', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Mother', 'ডামি মা', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Class', 'ডামি ক্লাস', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Degree', 'ডামি ডিগ্রি', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Guardian Number', 'ডামি গার্ডিয়ন নম্বর', 'اسم وهمي'
-- );


-- INSERT INTO translations (
--     translation_text, bn_text, ar_text
-- ) VALUES (
--     'Dummy Image Path', 'ডামি ছবি পথ', 'اسم وهمي'
-- );


-- -- Insert into transactions table (donation)
-- INSERT INTO transactions (
--     transaction_id, user_id, type, month, amount, date
-- ) VALUES (
--     9999, 9999, 'donations', 9, 9999.0, '2009-09-09'
-- );

-- -- Insert into transactions table (generic transaction)
-- INSERT INTO transactions (
--     transaction_id, user_id, type, amount, date
-- ) VALUES (
--     999, 9999, 'fees', 9999.0, '2009-09-09'
-- );

-- -- Insert into payments table
-- INSERT INTO payments (
--     payment_id, user_id, food, special_food, reduced_fee, due_months, tax
-- ) VALUES (
--     9999, 9999, 1, 1, 99.0, 9, 9.0
-- );
