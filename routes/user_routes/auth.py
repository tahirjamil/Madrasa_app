from flask import request, jsonify, render_template
from . import user_routes
import pymysql.cursors
from werkzeug.security import generate_password_hash, check_password_hash
from pymysql.err import IntegrityError
import pymysql
from database import connect_to_db
from logger import log_event
from helpers import (validate_fullname, validate_password, auto_delete_users,
send_sms, format_phone_number,
generate_code, check_code, send_email, get_email)
from translations import t
import datetime, os
from datetime import timedelta, datetime as dt


# ========== Routes ==========
@user_routes.route("/register", methods=["POST"])
def register():
    conn = connect_to_db()

    data = request.get_json()
    fullname = data.get("fullname", "").strip()
    email = data.get("email")
    phone = data.get("phone")
    password = data.get("password")
    user_code = data.get("code")
    lang = data.get("language") or data.get("Language") or "en"

    if not fullname or not phone or not password or not user_code:
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": t("all_fields_including_code_required", lang)}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": t("invalid_phone_format", lang)}), 400

    validate_code = check_code(user_code, formatted_phone)
    if validate_code:
        return validate_code

    hashed_password = generate_password_hash(password)
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        try:
            cursor.execute(
                "INSERT INTO users (fullname, phone, password, email) VALUES (%s, %s, %s, %s)",
                (fullname, formatted_phone, hashed_password, email)
            )
            conn.commit()

            cursor.execute(
                "SELECT id FROM users WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
                (fullname, formatted_phone)
            )
            result = cursor.fetchone()
            user_id = result['id'] if result else None
            conn.commit()

            cursor.execute(
                "SELECT * FROM people WHERE LOWER(name_en) = LOWER(%s) AND phone = %s",
                (fullname, formatted_phone)
            )
            people_result = cursor.fetchone()

            if people_result:
                cursor.execute(
                    "UPDATE people SET id = %s WHERE LOWER(name_en) = LOWER(%s) AND phone = %s",
                    (user_id, fullname, formatted_phone)
                )
                conn.commit()

            return jsonify({
                "success": True, "message": t("registration_successful", lang),
                "info": people_result
                }), 201

        except IntegrityError:
            return jsonify({"message": t("user_already_registered", lang)}), 400
        except Exception as e:
            return jsonify({"message": t("internal_server_error", lang), "error": str(e)}), 500


@user_routes.route("/login", methods=["POST"])
def login():
    conn = connect_to_db()

    data = request.get_json()
    fullname = data.get("fullname", "").strip()
    phone = data.get("phone")
    password = data.get("password")
    lang = data.get("language") or "en"

    if not fullname or not phone or not password:
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": t("all_fields_required", lang)}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        log_event("auth_invalid_phone", phone, "Invalid phone format")
        return jsonify({"message": t("invalid_phone_format", lang)}), 400

    try:
        with conn.cursor(cursor=pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, deactivated_at, password FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = cursor.fetchone()

            if not user:
                log_event("auth_user_not_found", formatted_phone, f"User {fullname} not found")
                return jsonify({"message": t("user_not_found", lang)}), 404
            
            if not check_password_hash(user["password"], password):
                log_event("auth_incorrect_password", formatted_phone, "Incorrect password")
                return jsonify({"message": t("incorrect_password", lang)}), 401
            
            if user["deactivated_at"] is not None:
                return jsonify({"message": t("account_deactivated", lang)}), 403 #TODO: in app
            
            cursor.execute(
                """
                SELECT u.id, u.fullname, u.phone, p.acc_type AS userType, p.*
                FROM users u
                LEFT JOIN people p ON p.id = u.id
                WHERE u.id = %s AND p.phone = %s AND p.name_en = %s
                """,
                (user["id"], formatted_phone, fullname)
            )
            info = cursor.fetchone()

            if not info or not info.get("phone"):
                log_event("auth_additional_info_required", formatted_phone, "Missing profile info")
                return jsonify({
                    "error": "incomplete_profile", 
                    "message": t("additional_info_required", lang)
                }), 422
            
            info.pop("password", None)
            dob = info.get("date_of_birth")
            if isinstance(dob, (datetime.date, datetime.datetime)):
                info["date_of_birth"] = dob.strftime("%d/%m/%Y")

            return jsonify({"success": True, "message": t("login_successful", lang), "info": info}), 200
            
    except Exception as e:
        log_event("auth_error", formatted_phone, str(e))
        return jsonify({"message": t("internal_server_error", lang)}), 500

    finally:
        conn.close()

@user_routes.route("/send_code", methods=["POST"])
def send_verification_code():
    conn = connect_to_db()
    SMS_LIMIT_PER_HOUR = 5
    EMAIL_LIMIT_PER_HOUR = 15

    data = request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname").strip()
    password = data.get("password")
    lang = data.get("language") or "en"
    signature = data.get("app_signature")
    email = data.get("email")

    if not phone or not fullname:
        return jsonify({"message": t("phone_and_fullname_required", lang)}), 400
    
    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": t("invalid_phone_format", lang)}), 400

    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if fullname:
                ok, msg = validate_fullname(fullname)
                if not ok:
                    return jsonify({"message": t(msg, lang)}), 400

            if password:
                ok, msg = validate_password(password)
                if not ok:
                    return jsonify({"message": t(msg, lang)}), 400
                
                cursor.execute("SELECT * FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)", (formatted_phone, fullname))
                if cursor.fetchone():
                    return jsonify({"message": t("user_already_registered", lang)}), 409
            
            if not email:
                email = get_email(phone=formatted_phone, fullname=fullname)

            # Rate limit check
            cursor.execute("""
                SELECT COUNT(*) AS recent_count 
                FROM verifications 
                WHERE phone = %s AND created_at > NOW() - INTERVAL 1 HOUR
            """, (formatted_phone,))
            result = cursor.fetchone()
            count = result["recent_count"] if result else 0

            # Send verification code
            code = generate_code()
            
            if count < SMS_LIMIT_PER_HOUR:
                    # Send SMS
                    if send_sms(phone=formatted_phone, signature=signature, code=code,):
                        cursor.execute(
                            "INSERT INTO verifications (phone, code) VALUES (%s, %s)",
                            (formatted_phone, code)
                        )
                        conn.commit()
                        return jsonify({"success": True, "message": t("verification_sms_sent", lang, target=formatted_phone)}), 200
                        # If SMS fails, fall back to email below

            # SMS limit reached or SMS failed => try EMAIL
            if email:
                if count < EMAIL_LIMIT_PER_HOUR:
                    if send_email(to_email=email, code=code, lang=lang):
                        cursor.execute(
                            "INSERT INTO verifications (phone, code) VALUES (%s, %s)",
                            (formatted_phone, code)
                        )
                        conn.commit()
                        return jsonify({"success": True, "message": t("verification_email_sent", lang, target=email)}), 200
                        # else fall through to failure
                else:
                    log_event("rate_limit_blocked", phone, "Both send limit exceeded")
                    return jsonify({"message": t("limit_reached", lang)}), 429

            # If we get here, both sends failed or no email provided
            log_event("verification_failed", phone, f"count={count}")
            return jsonify({"message": t("failed_to_send_verification_code", lang)}), 500

    except Exception as e:
        log_event("internal_error", formatted_phone, str(e))
        return jsonify({"message": t("internal_error", lang, error=str(e))}), 500
    

@user_routes.route("/reset_password", methods=["POST"])
def reset_password():
    conn = connect_to_db()
    
    data = request.get_json()
    phone = data.get("phone")
    fullname = data.get("fullname").strip()
    user_code = data.get("code")
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    lang = data.get("language") or data.get("Language") or "en"

    # Check required fields (except old_password and code, because one of them must be present)
    if not all([phone, fullname]):
        log_event("auth_missing_fields", phone, "Phone or fullname missing")
        return jsonify({"message": t("phone_fullname_new_password_required", lang)}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": t("invalid_phone_format", lang)}), 400

    # If old password is not provided, use code verification instead
    if not old_password:
        validate_code = check_code(user_code, formatted_phone)
        if validate_code:
            return validate_code
        elif not new_password:
            return jsonify({"success": True, "message": t("code_successfully_matched", lang)}), 200

    # Fetch the user
    with conn.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(
            "SELECT password FROM users WHERE phone = %s AND LOWER(fullname) = LOWER(%s)",
            (formatted_phone, fullname)
        )
        result = cursor.fetchone()

        if not result:
            return jsonify({"message": t("user_not_found", lang)}), 404

        # If old_password is given, check it
        if old_password:
            if not check_password_hash(result['password'], old_password):
                return jsonify({"message": t("incorrect_old_password", lang)}), 401
            
        hashed_password = generate_password_hash(new_password)

        if check_password_hash(result['password'], new_password):
            return jsonify({"message": t("password_same_error", lang)}), 400

        # Update the password
        cursor.execute(
            "UPDATE users SET password = %s WHERE LOWER(fullname) = LOWER(%s) AND phone = %s",
            (hashed_password, fullname, formatted_phone)
        )
        conn.commit()
        return jsonify({"success": True, "message": t("password_reset_successful", lang)}), 201

@user_routes.route("/account/<page_type>", methods=["GET", "POST"])
def manage_account(page_type):
    lang = request.get_json().get("language") or "en"
    # clean up any expired accounts
    auto_delete_users()

    if page_type not in ("remove", "deactivate"):
        return jsonify({"message": t("invalid_page_type", lang)}), 400

    if request.method == "GET":
        # Render the form
        return render_template(
            "account_manage.html",
            page_type=page_type.capitalize()
        )

    # POST: gather input
    data     = request.get_json() if request.method == "POST" else request.form
    phone    = data.get("phone", "").strip()
    fullname = (data.get("fullname") or "").strip()
    password = data.get("password", "")
    lang     = data.get("language") or "en"
    email    = data.get("email")

    if not phone or not fullname or not password:
        return jsonify({"message": t("all_fields_required", lang)}), 400

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"message": t("invalid_phone_number", lang)}), 400

    # lookup user
    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                "SELECT id, password FROM users "
                "WHERE phone=%s AND LOWER(fullname)=LOWER(%s)",
                (formatted_phone, fullname)
            )
            user = cursor.fetchone()

            if not user or not check_password_hash(user["password"], password):
                log_event("delete_invalid_credentials", formatted_phone, "Invalid credentials")
                return jsonify({"message": t("invalid_login_details", lang)}), 401

            # prepare confirmation message
            deletion_days = 30
            msg     = t("account_deletion_confirmation_msg", lang, days=deletion_days)
            subject = t("subject_deletion_confirmation", lang)
            if page_type == "Deactivate":
                msg     = t("account_deactivation_confirmation_msg", lang)
                subject = t("subject_deactivation_confirmation", lang)

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
                return jsonify({"message": t("could_not_send_confirmation", lang)}), 500

            # schedule deactivation/deletion
            now = datetime.datetime.utcnow()
            scheduled = now + timedelta(days=deletion_days)
            sql = "UPDATE users SET deactivated_at=%s"
            params = [now]
            if page_type == "remove":
                sql += ", scheduled_deletion_at=%s"
                params.append(scheduled)
            sql += " WHERE id=%s"
            params.append(user["id"])

            cursor.execute(sql, params)
            conn.commit()

        # success response
        if page_type == "remove":
            log_event("deletion_scheduled", formatted_phone, f"User {fullname} scheduled for deletion")
            return jsonify({"success": True, "message": t("account_deletion_initiated", lang)}), 200

        log_event("account_deactivated", formatted_phone, f"User {fullname} deactivated")
        return jsonify({"success": True, "message": t("account_deactivated_successfully", lang)}), 200

    except Exception as e:
        log_event("manage_account_error", phone, str(e))
        return jsonify({"message": t("an_error_occurred", lang)}), 500

    finally:
        conn.close()

@user_routes.route("/account/reactivate", methods=['POST'])
def undo_remove():
    data = request.get_json()
    phone = format_phone_number(data.get("phone"))
    fullname = data.get("fullname", "").strip()
    lang = data.get("language") or "en"

    if not phone or not fullname:
        return jsonify({"message": t("all_fields_required", lang)}), 400

    conn = connect_to_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, deactivated_at FROM users
                WHERE phone = %s AND LOWER(fullname) = LOWER(%s)
            """, (phone, fullname))
            user = cursor.fetchone()

            if not user or not user["deactivated_at"]:
                return jsonify({"message": "No deactivated account found"}), 404

            deactivated_at = user["deactivated_at"]
            if (datetime.datetime.now() - deactivated_at).days > 14 and user["scheduled_deletion_at"]:
                return jsonify({"message": "Undo period expired"}), 403

            cursor.execute("""
                UPDATE users
                SET deactivated_at = NULL,
                    scheduled_deletion_at = NULL
                WHERE id = %s
            """, (user["id"],))
            conn.commit()
        return jsonify({"success": True, "message": "Account reactivated"}), 200
    except Exception as e:
        log_event("account_reactivation_failed", phone, str(e))
        return jsonify({"message": t("account_reactivation_failed", lang)}), 500
    finally:
        conn.close()

@user_routes.route("/account/check", methods=['POST'])
def get_account_status():
    auto_delete_users()

    data = request.get_json()
    lang = data.get("language") or data.get("Language") or "en"

    LOGOUT_MSG = t("session_invalidated", lang)
    DEACTIVATE_MSG = t("account_deactivated", lang)

    device_id = data.get("device_id")
    device_brand = data.get("device_brand")
    ip_address = data.get("ip_address")

    phone        = format_phone_number(data.get("phone") or "")
    user_id      = data.get("user_id")
    fullname     = (data.get("name_en") or "").strip()
    member_id    = data.get("member_id")

    if not ip_address and not device_id and not device_brand:
        return jsonify({"action": "block", "message": t("unknown_device", lang)}), 400

    if not phone or not fullname:
        return jsonify({"success": True, "message": t("no_account_given", lang)}), 200

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

    conn = connect_to_db()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:

            cursor.execute("""
                    SELECT u.deactivated_at, u.email, p.*
                    FROM users u
                    JOIN people p ON p.id = u.id
                    WHERE u.phone = %s and u.fullname = %s
            """, (phone, fullname))
            record = cursor.fetchone()

        if not record:
            log_event("account_check_not_found", ip_address or user_id, "No matching user")
            return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401

        # Check deactivation
        if record.get("deactivated_at"):
            log_event("account_check_deactivated", record["id"], "Account deactivated")
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
                    log_event("account_check_bad_date", record["id"], f"Bad date: {provided}")
                    return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
                if db_val:
                    if db_val.date() != provided_date:
                        log_event("account_check_mismatch", record["id"], f"Mismatch: {col}: {provided_date} != {db_val}, so {fullname} logged out")
                        return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
            else:
                # cast both to strings for comparison
                if str(provided).strip() != str(db_val).strip():
                    log_event("account_check_mismatch", record["id"], f"Mismatch: {col}: {provided} != {db_val}, so {fullname} logged out")
                    return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401
                if db_val:
                    if db_val.date() != provided_date:
                        log_event("account_check_mismatch", record["id"], f"Mismatch: {col}: {provided_date} != {db_val}, so {fullname} logged out")
                        return jsonify({"action": "logout", "message": LOGOUT_MSG}), 401

        cursor.execute("SELECT open_times FROM interactions WHERE id = %s", (user_id))
        result = cursor.fetchall()
        conn.commit()

        try:
            if not result:
                cursor.execute("""INSERT INTO interactions 
                            (device_id, ip_address, device_brand, id)
                            VALUES
                            (%s, %s, %s, %s, %s)
                            """, (device_id, ip_address, device_brand, user_id))
            else:
                cursor.execute("SELECT open_times FROM interactions WHERE device_id = %s AND device_brand = %s AND id = %s", (user_id))
                open_times = cursor.fetchone()
                opened = open_times['open_times'] if open_times else 0
                
                opened += 1
                cursor.execute("""UPDATE interactions SET open_times = %s
                            WHERE device_id = %s AND device_brand = %s AND id = %s
                            """, (opened, device_id, device_brand, user_id))
        except pymysql.MySQLError as e:
            log_event("Saving interactions failed", phone, str(e))
        finally:
            conn.close()
                
            # all checks passed
        return jsonify({"success": True, "message": t("account_is_valid", lang), "id": record["id"]}), 200

    except Exception as e:
        log_event("account_check_error", phone, str(e))
        return jsonify({"message": t("internal_error", lang)}), 500

    finally:
        conn.close()