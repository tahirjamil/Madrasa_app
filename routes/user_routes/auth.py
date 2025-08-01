from quart import request, jsonify, render_template
from . import user_routes
from werkzeug.security import generate_password_hash, check_password_hash
from aiomysql import IntegrityError
from database.database_utils import get_db_connection
from logger import log_event_async as log_event
from helpers import (validate_fullname, validate_password,
    send_sms, format_phone_number, is_device_unsafe, is_test_mode,
    generate_code, check_code, send_email, get_email)
from quart_babel import gettext as _
import datetime, os, aiomysql
from datetime import timedelta, datetime as dt
from config import Config


# ========== Routes ==========
@user_routes.route("/register", methods=["POST"])
async def register():
    conn = await get_db_connection()

    data = await request.get_json()
    fullname = data.get("fullname", "").strip().lower()
    email = data.get("email")
    phone = data.get("phone")
    password = data.get("password")
    user_code = data.get("code")

    if is_test_mode():
        return jsonify({
            "success": True, "message": "Ignored because in test mode",
            "info": None
            }), 201
    
    # Device Verify
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")

    if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or email or fullname):
        return jsonify({"message": _("Unknown device detected")}), 400

    if not fullname or not phone or not password or not user_code:
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": _("All fields including code are required")}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": _("Invalid phone number format")}), 400

    validate_code = check_code(user_code, formatted_phone)
    if validate_code:
        return validate_code

    hashed_password = generate_password_hash(password)
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        try:
            await cursor.execute(
                "INSERT INTO users (fullname, phone, password, email, ip_address) VALUES (%s, %s, %s, %s, %s)",
                (fullname, formatted_phone, hashed_password, email, ip_address)
            )
            await conn.commit()

            await cursor.execute(
                "SELECT user_id FROM users WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
                (fullname, formatted_phone)
            )
            result = await cursor.fetchone()
            user_id = result['user_id'] if result else None
            await conn.commit()

            await cursor.execute(
                """SELECT 
                    p.*,

                    tname.en_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                    taddress.en_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                    tfather.en_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                    tmother.en_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar

                    FROM peoples p

                    JOIN translations tname ON tname.translation_text = p.name
                    LEFT JOIN translations taddress ON taddress.translation_text = p.address
                    JOIN translations tfather ON tfather.translation_text = p.father_name
                    LEFT JOIN translations tmother ON tmother.translation_text = p.mother_name

                    WHERE LOWER(p.name) = LOWER(%s) AND p.phone = %s""",
                (fullname, formatted_phone))
            people_result = await cursor.fetchone()

            if people_result:
                await cursor.execute(
                    "UPDATE peoples SET user_id = %s WHERE LOWER(name_en) = LOWER(%s) AND phone = %s",
                    (user_id, fullname, formatted_phone)
                )
                await conn.commit()

            return jsonify({
                "success": True, "message": _("Registration successful"),
                "info": people_result
                }), 201

        except IntegrityError:
            return jsonify({"message": _("User with this fullname and phone already registered")}), 400
        except Exception as e:
            return jsonify({"message": _("Internal server error"), "error": str(e)}), 500


@user_routes.route("/login", methods=["POST"])
async def login():
    conn = await get_db_connection()

    data = await request.get_json()
    fullname = data.get("fullname", "").strip().lower()
    phone = data.get("phone")
    password = data.get("password")

    if is_test_mode():
        fullname = Config.dummy_fullname
        phone = Config.dummy_phone
        password = Config.dummy_password

    # Device Verify
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")

    if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or fullname):
        return jsonify({"message": _("Unknown device detected")}), 400

    if not fullname or not phone or not password:
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": _("All fields are required")}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        log_event("auth_invalid_phone", phone, "Invalid phone format")
        return jsonify({"message": _("Invalid phone number format")}), 400

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT user_id, deactivated_at, password FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()

            if not user:
                log_event("auth_user_not_found", formatted_phone, f"User {fullname} not found")
                return jsonify({"message": _("User not found")}), 404
            
            if not check_password_hash(user["password"], password):
                log_event("auth_incorrect_password", formatted_phone, "Incorrect password")
                return jsonify({"message": _("Incorrect password")}), 401
            
            if user["deactivated_at"] is not None:
                return jsonify({"action": "deactivate", "message": _("Account is deactivated")}), 403 #TODO: in app
            
            await cursor.execute(
                """
                SELECT u.user_id, u.fullname, u.phone, p.acc_type AS userType, p.*

                tname.en_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                taddress.en_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                tfather.en_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                tmother.en_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar

                FROM users u
                JOIN peoples p ON p.user_id = u.user_id
                JOIN translations tname ON tname.translation_text = p.name
                LEFT JOIN translations taddress ON taddress.translation_text = p.address
                JOIN translations tfather ON tfather.translation_text = p.father_name
                LEFT JOIN translations tmother ON tmother.translation_text = p.mother_name

                WHERE u.user_id = %s AND p.phone = %s AND p.name = %s
                """,
                (user["user_id"], formatted_phone, fullname)
            )
            info = await cursor.fetchone()

            if not info or not info.get("phone") or not info.get("user_id"):
                log_event("auth_additional_info_required", formatted_phone, "Missing profile info")
                return jsonify({
                    "error": "incomplete_profile", 
                    "message": _("Additional info required")
                }), 422
            
            info.pop("password", None)
            dob = info.get("date_of_birth")
            if isinstance(dob, (datetime.date, datetime.datetime)):
                info["date_of_birth"] = dob.strftime("%d/%m/%Y")

            return jsonify({"success": True, "message": _("Login successful"), "info": info}), 200
            
    except Exception as e:
        log_event("auth_error", formatted_phone, str(e))
        return jsonify({"message": _("Internal server error")}), 500

@user_routes.route("/send_code", methods=["POST"])
async def send_verification_code():

    conn = await get_db_connection()
    SMS_LIMIT_PER_HOUR = 5
    EMAIL_LIMIT_PER_HOUR = 15

    data = await request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname").strip().lower()
    password = data.get("password")
    lang = data.get("language") or "en"
    signature = data.get("app_signature")
    email = data.get("email")

    if is_test_mode() or code == "123456":
        return jsonify({"success": True, "message": _("Verification code sent to %(target)s") % {"target": Config.dummy_email}}), 200

    # Device Verify
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")

    if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or email or fullname):
        return jsonify({"message": _("Unknown device detected")}), 400

    if not phone or not fullname:
        return jsonify({"message": _("Phone number and fullname required")}), 400
    
    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": _("Invalid phone number format")}), 400

    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            if fullname:
                ok, msg = validate_fullname(fullname)
                if not ok:
                    return jsonify({"message": _(msg)}), 400

            if password:
                ok, msg = validate_password(password)
                if not ok:
                    return jsonify({"message": _(msg)}), 400
                
                await cursor.execute("SELECT * FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)", (formatted_phone, fullname))
                if await cursor.fetchone():
                    return jsonify({"message": _("User with this fullname and phone already registered")}), 409
            
            if not email:
                email = get_email(phone=formatted_phone, fullname=fullname)

            # Rate limit check - Combined limit for both SMS and email
            await cursor.execute("""
                SELECT COUNT(*) AS recent_count 
                FROM verifications 
                WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
            """, (formatted_phone,))
            result = await cursor.fetchone()
            count = result["recent_count"] if result else 0
            
            # Check if rate limit exceeded for all methods
            if count >= max(SMS_LIMIT_PER_HOUR, EMAIL_LIMIT_PER_HOUR):
                log_event("rate_limit_blocked", phone, "All verification methods limit exceeded")
                return jsonify({"message": _("Limit reached. Try again later.")}), 429

            # Send verification code
            code = generate_code()
            sql = "INSERT INTO verifications (phone, code, ip_address) VALUES (%s, %s, %s)"
            params = (formatted_phone, code, ip_address)
            
            verification_sent = False
            
            # Try SMS first if under SMS limit
            if count < SMS_LIMIT_PER_HOUR:
                if send_sms(phone=formatted_phone, signature=signature, code=code):
                    await cursor.execute(sql, params)
                    await conn.commit()
                    return jsonify({"success": True, "message": _("Verification code sent to %(target)s") % {"target": formatted_phone}}), 200

            # Try email if SMS failed or limit reached, but under email limit
            if email and count < EMAIL_LIMIT_PER_HOUR:
                if send_email(to_email=email, code=code, lang=lang):
                    await cursor.execute(sql, params)
                    await conn.commit()
                    return jsonify({"success": True, "message": _("Verification code sent to %(target)s") % {"target": email}}), 200

            # If we get here, both methods failed or no email provided
            log_event("verification_failed", phone, f"count={count}")
            return jsonify({"message": _("Failed to send verification code")}), 500

    except Exception as e:
        log_event("internal_error", formatted_phone, str(e))
        return jsonify({"message": _("Internal error: %(error)s") % {"error": str(e)}}), 500
    

@user_routes.route("/reset_password", methods=["POST"])
async def reset_password():

    conn = await get_db_connection()
    
    data = await request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname").strip().lower()
    user_code = data.get("code")
    old_password = data.get("old_password")
    new_password = data.get("new_password")


    if is_test_mode():
        if not new_password:
            return jsonify({"success": True, "message": "App in test mode"}), 200
        else:
            return jsonify({"success": True, "message": "App in test mode"}), 201
        
    # Device Verify
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")

    if is_device_unsafe(ip_address=ip_address, device_id=device_id, info=phone or fullname):
        return jsonify({"message": _("Unknown device detected")}), 400
    
    # Check required fields (except old_password and code, because one of them must be present)
    if not all([phone, fullname]):
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": _("Phone, Fullname, and New Password are required")}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": _("Invalid phone number format")}), 400

    # If old password is not provided, use code verification instead
    if not old_password:
        validate_code = check_code(user_code, formatted_phone)
        if validate_code:
            return validate_code
        elif not new_password:
            return jsonify({"success": True, "message": _("Code successfully matched")}), 200

    # Fetch the user
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute(
            "SELECT password FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
            (formatted_phone, fullname)
        )
        result = await cursor.fetchone()

        if not result:
            return jsonify({"message": _("User not found")}), 404

        # If old_password is given, check it
        if old_password:
            if not check_password_hash(result['password'], old_password):
                return jsonify({"message": _("Incorrect old password")}), 401
            
        hashed_password = generate_password_hash(new_password)

        if check_password_hash(result['password'], new_password):
            return jsonify({"message": _("New password cannot be the same as the current password.")}), 400

        # Update the password
        await cursor.execute(
            "UPDATE users SET password = %s, ip_address = %s WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
            (hashed_password, ip_address, fullname, formatted_phone)
        )
        await conn.commit()
        return jsonify({"success": True, "message": _("Password Reset Successful")}), 201

@user_routes.route("/account/<page_type>", methods=["GET", "POST"])
async def manage_account(page_type):

    if page_type not in ("remove", "deactivate"):
        return jsonify({"message": _("Invalid page type")}), 400

    if request.method == "GET":
        # Render the form
        return render_template(
            "account_manage.html",
            page_type=page_type.capitalize()
        )

    # POST: gather input
    data     = request.get_json() if request.method == "POST" else request.form
    phone    = data.get("phone", "").strip()
    fullname = (data.get("fullname") or "").strip().lower()
    password = data.get("password", "")
    email    = data.get("email")

    if is_test_mode():
        fullname = Config.dummy_fullname
        phone = Config.dummy_phone
        password = Config.dummy_password


    if not phone or not fullname or not password:
        return jsonify({"message": _("All fields are required")}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": _("Invalid phone number")}), 400

    # lookup user
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(
                "SELECT user_id, password FROM users "
                "WHERE phone=%s AND LOWER(fullname)=LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = await cursor.fetchone()

            if not user or not check_password_hash(user["password"], password):
                log_event("delete_invalid_credentials", formatted_phone, "Invalid credentials")
                return jsonify({"message": _("Invalid login details")}), 401

            # prepare confirmation message
            deletion_days = 30
            msg     = _("Your account has been successfully put for deletion.\nIt will take %(days)d days to fully delete your account.\nIf it wasn't you, please contact us for account recovery.\n\n@An-Nur.app") % {"days": deletion_days}
            subject = _("Account Deletion Confirmation")
            if page_type == "Deactivate":
                msg     = _("Your account has been successfully deactivated.\nYou can reactivate it within our app.\nIf it wasn't you, please contact us immediately.\n\n@An-Nur.app")
                subject = _("Account Deactivation Confirmation")

            # send notifications
            errors = 0
            if email:
                if not send_email(to_email=email, subject=subject, body=msg):
                    errors += 1
                    log_event("notify_email_failed", formatted_phone, "Email send failed")
            else:
                errors += 1

            if not send_sms(phone=formatted_phone, msg=msg):
                errors += 1
                log_event("notify_sms_failed", formatted_phone, "SMS send failed")

            if errors > 1:
                return jsonify({"message": _("Could not send confirmation. Try again later.")}), 500

            # schedule deactivation/deletion
            now = datetime.datetime.now(datetime.timezone.utc)
            scheduled = now + timedelta(days=deletion_days)
            sql = "UPDATE users SET deactivated_at=%s"
            params = [now]
            if page_type == "remove":
                sql += ", scheduled_deletion_at=%s"
                params.append(scheduled)
            sql += " WHERE user_id=%s"
            params.append(user["user_id"])

            await cursor.execute(sql, params)
            await conn.commit()

        # success response
        if page_type == "remove":
            log_event("deletion_scheduled", formatted_phone, f"User {fullname} scheduled for deletion")
            return jsonify({"success": True, "message": _("Account deletion initiated. Check your messages.")}), 200

        log_event("account_deactivated", formatted_phone, f"User {fullname} deactivated")
        return jsonify({"success": True, "message": _("Account deactivated successfully.")}), 200

    except Exception as e:
        log_event("manage_account_error", phone, str(e))
        return jsonify({"message": _("An error occurred")}), 500

@user_routes.route("/account/reactivate", methods=['POST'])
async def undo_remove():

    if is_test_mode():
        return jsonify({"success": True, "message": "App in test mode"}), 200
    
    data = await request.get_json()
    phone = format_phone_number(data.get("phone"))
    fullname = data.get("fullname", "").strip().lower()

    if not phone or not fullname:
        return jsonify({"message": _("All fields are required")}), 400

    conn = await get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT user_id, deactivated_at FROM users
                WHERE phone = %s AND LOWER(fullname) = LOWER(%s)
            """, (phone, fullname))
            user = await cursor.fetchone()

            if not user or not user["deactivated_at"]:
                return jsonify({"message": "No deactivated account found"}), 404

            deactivated_at = user["deactivated_at"]
            if (datetime.datetime.now() - deactivated_at).days > 14 and user["scheduled_deletion_at"]:
                return jsonify({"message": "Undo period expired"}), 403

            await cursor.execute("""
                UPDATE users
                SET deactivated_at = NULL,
                    scheduled_deletion_at = NULL
                WHERE user_id = %s
            """, (user["user_id"],))
            await conn.commit()
        return jsonify({"success": True, "message": _("Account reactivated.")}), 200
    except Exception as e:
        log_event("account_reactivation_failed", phone, str(e))
        return jsonify({"message": _("Account reactivation failed.")}), 500

@user_routes.route("/account/check", methods=['POST'])
async def get_account_status():
    data = await request.get_json()

    if is_test_mode():
        return jsonify({"success": True, "message": "App in test mode."}), 200

    LOGOUT_MSG = _("Session invalidated. Please log in again.")
    DEACTIVATE_MSG = _("Account is deactivated")

    device_id = data.get("device_id")
    device_brand = data.get("device_brand")
    ip_address = data.get("ip_address")

    phone        = format_phone_number(data.get("phone") or "")
    user_id      = data.get("user_id")
    fullname     = (data.get("name_en") or "").strip().lower()
    member_id    = data.get("member_id")

    if not ip_address and not device_id and not device_brand:
        return jsonify({"action": "block", "message": _("Unknown device detected")}), 400

    if not phone or not fullname:
        return jsonify({"success": True, "message": _("No account information provided.")}), 200

    checks = {
        "member_id":     member_id,
        "student_id":    data.get("student_id"),
        "name_en":       fullname,
        "name_bn":       data.get("name_bn"),
        "name_ar":       data.get("name_ar"),
        "date_of_birth": data.get("date_of_birth"),
        "birth_certificate": data.get("birth_certificate"),
        "national_id":   data.get("national_id"),
        "blood_group":   data.get("blood_group"),
        "gender":        data.get("gender"),
        "title1":        data.get("title1"),
        "title2":        data.get("title2"),
        "source":        data.get("source"),
        "present_address":    data.get("present_address"),
        "address_en":    data.get("address_en"),
        "address_bn":    data.get("address_bn"),
        "address_ar":    data.get("address_ar"),
        "permanent_address":  data.get("permanent_address"),
        "father_or_spouse":   data.get("father_or_spouse"),
        "father_en":     data.get("father_en"),
        "father_bn":     data.get("father_bn"),
        "father_ar":     data.get("father_ar"),
        "mother_en":     data.get("mother_en"),
        "mother_bn":     data.get("mother_bn"),
        "mother_ar":     data.get("mother_ar"),
        "class":         data.get("class_name"),
        "guardian_number": data.get("guardian_number"),
        "available":     data.get("available"),
        "degree":        data.get("degree"),
        "image_path":    data.get("image_path"),
        "acc_type":      data.get("acc_type"),
        "is_donor":      data.get("is_donor"),
        "is_badri_member": data.get("is_badri_member"),
        "is_foundation_member": data.get("is_foundation_member"),
    }

    for c in checks:
        if checks[c] is None:
            log_event("account_check_missing_field", ip_address, f"Field {c} is missing")
            return jsonify({"action": "logout", "message": LOGOUT_MSG}), 400

    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:

            await cursor.execute("""
                    SELECT u.deactivated_at, u.email, p.*,

                    tname.en_text AS name_en, tname.bn_text AS name_bn, tname.ar_text AS name_ar,
                    taddress.en_text AS address_en, taddress.bn_text AS address_bn, taddress.ar_text AS address_ar,
                    tfather.en_text AS father_en, tfather.bn_text AS father_bn, tfather.ar_text AS father_ar,
                    tmother.en_text AS mother_en, tmother.bn_text AS mother_bn, tmother.ar_text AS mother_ar

                    FROM users u
                    JOIN peoples p ON p.user_id = u.user_id
                    JOIN translations tname ON tname.translation_text = p.name
                    LEFT JOIN translations taddress ON taddress.translation_text = p.address
                    LEFT JOIN translations tfather ON tfather.translation_text = p.father_name
                    LEFT JOIN translations tmother ON tmother.translation_text = p.mother_name

                    WHERE u.phone = %s and LOWER(u.fullname) = LOWER(%s)
            """, (phone, fullname))
            record = await cursor.fetchone()

        if not record:
            log_event("account_check_not_found", ip_address or user_id, "No matching user")
            return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401

        # Check deactivation
        if record.get("deactivated_at"):
            log_event("account_check_deactivated", record["user_id"], "Account deactivated")
            return jsonify({"action": "deactivate", "message": DEACTIVATE_MSG}), 401

        # Compare fields
        for col, provided in checks.items():
            if provided is None:
                continue   # skip fields not sent by client
            db_val = record.get(col)
            # special handling for dates: compare only date part
            if col == "date_of_birth" and isinstance(db_val, (datetime)):
                try:
                    provided_date = dt.fromisoformat(provided).date()
                except Exception:
                    log_event("account_check_bad_date", record["user_id"], f"Bad date: {provided}")
                    return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
                if db_val:
                    if db_val.date() != provided_date:
                        log_event("account_check_mismatch", record["user_id"], f"Mismatch: {col}: {provided_date} != {db_val}, so {fullname} logged out")
                        return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
            else:
                # cast both to strings for comparison
                try:
                    provided_date = dt.fromisoformat(provided).date()
                except Exception:
                    log_event("account_check_bad_date", record["user_id"], f"Bad date: {provided}")
                    return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
                if str(provided).strip() != str(db_val).strip():
                    log_event("account_check_mismatch", record["user_id"], f"Mismatch: {col}: {provided} != {db_val}, so {fullname} logged out")
                    return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
                if db_val:
                    if db_val.date() != provided_date:
                        log_event("account_check_mismatch", record["user_id"], f"Mismatch: {col}: {provided_date} != {db_val}, so {fullname} logged out")
                        return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401

        await cursor.execute("SELECT open_times FROM interactions WHERE device_id = %s AND device_brand = %s AND user_id = %s LIMIT 1", (device_id, device_brand, record["user_id"]))
        open_times = await cursor.fetchone()

        try:
            if not open_times:
                await cursor.execute("""INSERT INTO interactions 
                            (device_id, ip_address, device_brand, user_id)
                            VALUES
                            (%s, %s, %s, %s)
                            """, (device_id, ip_address, device_brand, user_id))
            else:
                opened = open_times['open_times'] if open_times else 0
                
                opened += 1
                await cursor.execute("""UPDATE interactions SET open_times = %s
                            WHERE device_id = %s AND device_brand = %s AND user_id = %s
                            """, (opened, device_id, device_brand, user_id))
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            log_event("Saving interactions failed", phone, str(e))
                
            # all checks passed
        return jsonify({"success": True, "message": _("Account is valid"), "user_id": record["user_id"]}), 200

    except Exception as e:
        log_event("account_check_error", phone, str(e))
        return jsonify({"message": _("Internal error")}), 500