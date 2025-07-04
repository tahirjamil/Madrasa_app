TRANSLATIONS = {
    "verification_sms_sent": {
        "en": "Verification code sent to {target}",
        "bn": "{target} নম্বরে ভেরিফিকেশন কোড পাঠানো হয়েছে",
        "ar": "تم إرسال رمز التحقق إلى {target}"
    },
    "verification_email_sent": {
        "en": "Verification code sent to {target}",
        "bn": "{target} ঠিকানায় ভেরিফিকেশন কোড পাঠানো হয়েছে",
        "ar": "تم إرسال رمز التحقق إلى {target}"
    },
    "limit_reached": {
        "en": "Limit reached. Try again later.",
        "bn": "সীমা অতিক্রম হয়েছে। অনুগ্রহ করে পরে চেষ্টা করুন।",
        "ar": "تم الوصول إلى الحد. حاول مرة أخرى لاحقًا."
    },
    "invalid_phone_format": {
        "en": "Invalid phone number format",
        "bn": "নম্বরের ফরম্যাট সঠিক নয়",
        "ar": "تنسيق رقم الهاتف غير صالح"
    },
    "user_not_found": {
        "en": "User not found",
        "bn": "ব্যবহারকারী পাওয়া যায়নি",
        "ar": "المستخدم غير موجود"
    },
    "incorrect_password": {
        "en": "Incorrect password",
        "bn": "পাসওয়ার্ড ভুল",
        "ar": "كلمة المرور غير صحيحة"
    },
    "internal_server_error": {
        "en": "Internal server error",
        "bn": "সার্ভারে ত্রুটি হয়েছে",
        "ar": "خطأ في الخادم الداخلي"
    },
    "password_same_error": {
        "en": "New password cannot be the same as the current password.",
        "bn": "নতুন পাসওয়ার্ড পূর্বের পাসওয়ার্ডের সাথে একই হতে পারে না।",
        "ar": "لا يمكن أن تكون كلمة المرور الجديدة مثل الكلمة الحالية."
    }
}

def t(key, lang, **kwargs):
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get("en")  # fallback to English
    if kwargs:
        return text.format(**kwargs)
    return text
