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
    }
}

def t(key, lang, **kwargs):
    """Get translated text with optional formatting"""
    entry = TRANSLATIONS.get(key, {})
    text = entry.get(lang) or entry.get("en")  # fallback to English
    if kwargs:
        return text.format(**kwargs)
    return text
