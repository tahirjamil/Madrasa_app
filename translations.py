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
    },
    "account_deletion_confirmation_msg": {
        "en": (
            "Your account has been successfully put for deletion.\n"
            "It will take {days} days to fully delete your account.\n"
            "If it wasn’t you, please contact us for account recovery.\n\n@annur.app"
        ),
        "bn": (
            "আপনার অ্যাকাউন্ট ডিলিশনের জন্য সংরক্ষণ করা হয়েছে।\n"
            "আপনার অ্যাকাউন্ট সম্পূর্ণ মুছে ফেলার জন্য এটি {days} দিন সময় নিবে।\n"
            "যদি এটি আপনি না হন, তাহলে দয়া করে অ্যাকাউন্ট উদ্ধার করতে আমাদের সাথে যোগাযোগ করুন।\n\n@annur.app"
        ),
        "ar": (
            "تم وضع حسابك ليتم حذفه بنجاح.\n"
            "سيستغرق حذف حسابك بالكامل {days} يومًا.\n"
            "إذا لم تكن أنت، فيرجى الاتصال بنا لاستعادة الحساب.\n\n@annur.app"
        )
    },
    "subject_deletion_confirmation": {
        "en": "Account Deletion Confirmation",
        "bn": "নিশ্চিতকরণ: অ্যাকাউন্ট মুছে ফেলা",
        "ar": "تأكيد حذف الحساب"
    },
    "account_deactivation_confirmation_msg": {
        "en": (
            "Your account has been successfully deactivated.\n"
            "You can reactivate it within our app.\n"
            "If it wasn’t you, please contact us immediately.\n\n@annur.app"
        ),
        "bn": (
            "আপনার অ্যাকাউন্ট সফলভাবে নিষ্ক্রিয় করা হয়েছে।\n"
            "আপনি আমাদের অ্যাপে এটি পুনরায় চালু করতে পারবেন।\n"
            "যদি এটি আপনি না হন, দয়া করে অবিলম্বে আমাদের সাথে যোগাযোগ করুন।\n\n@annur.app"
        ),
        "ar": (
            "تم تعطيل حسابك بنجاح.\n"
            "يمكنك إعادة تنشيطه ضمن تطبيقنا.\n"
            "إذا لم تكن أنت، يرجى الاتصال بنا فورًا.\n\n@annur.app"
        )
    },
    "subject_deactivation_confirmation": {
        "en": "Account Deactivation Confirmation",
        "bn": "নিশ্চিতকরণ: অ্যাকাউন্ট নিষ্ক্রিয়করণ",
        "ar": "تأكيد تعطيل الحساب"
    }
}

def t(key, lang, **kwargs):
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get("en")  # fallback to English
    if kwargs:
        return text.format(**kwargs) if text else key
    return text if text else key
