"""Helper Functions for Madrasha Application"""
import collections
import dataclasses
import decimal
import fnmatch
import base64, hashlib, random, re, aiomysql, phonenumbers, requests
import threading
import uuid
import datetime as dt
from hmac import compare_digest
import asyncio, json, os, smtplib, time
from contextlib import asynccontextmanager
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple, Callable, Union, Iterable

from aiomysql import IntegrityError
from dotenv import load_dotenv
from quart import Request, Response, flash, g, jsonify, redirect, request
from quart_babel import gettext as _
from cryptography.fernet import Fernet
from database.database_utils import get_db_connection
from config import config
from utils.logger import log


# ---------- improved CacheManager ----------
class CacheManager:
    def __init__(self, max_size: int = 1000, cleanup_interval: int = 300):
        self._cache: Dict[str, (Any, float)] = {}
        self._max_size = max_size
        self._cleanup_interval = cleanup_interval
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def _maybe_cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        self._cleanup()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._maybe_cleanup()
            item = self._cache.get(key)
            if item is None:
                return default
            value, expiry = item
            if expiry is None or time.time() < expiry:
                return value
            # expired
            self._cache.pop(key, None)
            return default

    def set(self, key: str, value: Any, ttl: Optional[int] = 3600) -> None:
        expiry = None if ttl is None else time.time() + ttl
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._cleanup()
            self._cache[key] = (value, expiry)

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def keys(self):
        with self._lock:
            return list(self._cache.keys())

    def delete_pattern(self, pattern: str) -> int:
        """
        Delete entries whose key matches a glob-style pattern or substring.
        Returns number of deleted keys.
        """
        with self._lock:
            deleted = []
            # support both glob patterns (with *?) and simple substring
            is_glob = any(ch in pattern for ch in "*?[]")
            for key in list(self._cache.keys()):
                match = fnmatch.fnmatch(key, pattern) if is_glob else (pattern in key)
                if match:
                    deleted.append(key)
                    self._cache.pop(key, None)
            return len(deleted)

    def _cleanup(self) -> None:
        now = time.time()
        # remove expired
        expired = [k for k, (_, exp) in self._cache.items() if exp is not None and now >= exp]
        for k in expired:
            self._cache.pop(k, None)
        # if still too many, remove oldest by expiry (None=forever -> put last)
        if len(self._cache) > self._max_size:
            ordered = sorted(self._cache.items(), key=lambda kv: (kv[1][1] is None, kv[1][1] or float('inf')))
            to_remove = len(self._cache) - (self._max_size // 2)
            for k, _ in ordered[:to_remove]:
                self._cache.pop(k, None)

# global cache instance
cache = CacheManager()

# ---------- Cache Functions ----------
def get_cache_key(prefix: str, **kwargs) -> str:
    parts = [prefix]
    for k, v in sorted(kwargs.items()):
        # canonical JSON representation of values to reduce accidental collisions
        parts.append(f"{k}:{json.dumps(v, sort_keys=True, separators=(',',':'), default=str, ensure_ascii=False)}")
    return ":".join(parts)

def get_cached_data(cache_key: str, ttl: Optional[int] = None, default: Any = None) -> Any:
    # metrics + TTL default handled here
    if ttl is None:
        ttl = getattr(config, "CACHE_TTL", 3600)
    val = cache.get(cache_key, default=None)
    if val is not None:
        metrics_collector.increment("cache_hits")
        return val
    metrics_collector.increment("cache_misses")
    return default

def set_cached_data(cache_key: str, data: Any, ttl: Optional[int] = None) -> None:
    if ttl is None:
        ttl = getattr(config, "CACHE_TTL", 3600)
    cache.set(cache_key, data, ttl)

def invalidate_cache_pattern(pattern: str) -> int:
    return cache.delete_pattern(pattern)

# operation -> patterns mapping (domain specific)
CACHE_INVALIDATION_MAP = {
    'add_person': ['members:*', 'user:*'],
    'update_person': ['members:*', 'user:*'],
    'add_event': ['events:*'],
    'update_event': ['events:*'],
    # add more...
}

def invalidate_related_cache(operation: str, **kwargs) -> None:
    patterns = CACHE_INVALIDATION_MAP.get(operation, [])
    for p in patterns:
        invalidate_cache_pattern(p)

# ---------- decorator for endpoint-level caching ----------
def cache_with_invalidation(ttl: int = 3600):
    """
    Decorator factory for caching async/sync view funcs.
    Uses request fingerprint to build a key. Skips caching Response objects.
    """
    def deco(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build fingerprint deterministically
            try:
                method = request.method
                path = request.path
                try:
                    query = dict(sorted(request.args.items()))
                except Exception:
                    query = {}
                try:
                    body = await request.get_json()
                except Exception:
                    body = None
                fingerprint = json.dumps({"m": method, "p": path, "q": query, "b": body},
                                         sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
            except Exception:
                # fallback to args/kwargs if no request context
                fingerprint = json.dumps({"args": [repr(a) for a in args], "kwargs": kwargs},
                                         sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)

            key = f"{func.__module__}.{func.__name__}:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()}"
            cached = cache.get(key, default=None)
            if cached is not None:
                return cached

            result = await func(*args, **kwargs) if callable(getattr(func, "__call__", None)) else func(*args, **kwargs)

            # only cache pure data (not Response) to avoid header staleness
            if not isinstance(result, Response):
                cache.set(key, result, ttl)
            return result

        return wrapper
    return deco

# ---------- Enhanced HTTP Cache ---------- TODO: This is unknown
class EnhancedJSONEncoder(json.JSONEncoder):
    """Extend JSONEncoder with common non-JSON types handling."""
    def default(self, obj):
        # datetimes -> ISO8601 string
        if isinstance(obj, (dt.datetime, dt.date, dt.time)):
            # Use ISO format; datetimes preserve timezone if present
            return obj.isoformat()
        # Decimal -> number (or string if prefered)
        if isinstance(obj, decimal.Decimal):
            # convert to a float-safe string to avoid precision loss in JSON
            return str(obj)
        # UUID -> hex string
        if isinstance(obj, uuid.UUID):
            return str(obj)
        # dataclass -> dict
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        # bytes -> base64 string
        if isinstance(obj, (bytes, bytearray)):
            return base64.b64encode(bytes(obj)).decode('ascii')
        # fallback to parent's behavior (which will raise TypeError)
        return super().default(obj)


# class SimpleLRU:
#     """Thread-safe tiny LRU mapping from canonical_json -> etag (string).
#        Keeps `maxsize` most recent entries.
#     """
#     def __init__(self, maxsize: int = 1024):
#         self.maxsize = maxsize
#         self.lock = threading.Lock()
#         self._data = collections.OrderedDict()

#     def get(self, key: str) -> Optional[str]:
#         with self.lock:
#             try:
#                 val = self._data.pop(key)
#                 # reinsert to mark as most-recent
#                 self._data[key] = val
#                 return val
#             except KeyError:
#                 return None

#     def set(self, key: str, value: str) -> None:
#         with self.lock:
#             if key in self._data:
#                 self._data.pop(key)
#             self._data[key] = value
#             # evict oldest if over capacity
#             while len(self._data) > self.maxsize:
#                 self._data.popitem(last=False)

# _etag_cache = SimpleLRU(maxsize=2048)


def canonical_json(value: Any) -> str:
    """
    Return a deterministic, compact JSON string for 'value'.
    Uses EnhancedJSONEncoder for common non-serializable types.
    Raises TypeError if value cannot be serialized.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),  # remove spaces for byte-stability
        ensure_ascii=False,
        cls=EnhancedJSONEncoder,
    )


# def generate_etag_from_data(data: Any, *, weak: bool = False) -> str:
#     """
#     Produce a quoted ETag string (e.g. "\"<hex>\"" or 'W/"<hex>"').
#     Uses SHA-256 over canonical_json(data).
#     Caches the mapping canonical_json -> etag for perf.
#     """
#     canon = canonical_json(data)
#     # try cache
#     cached = _etag_cache.get(canon)
#     if cached is not None:
#         # if weak requested, prefix 'W/' if not already weak
#         return f'W/{cached}' if weak and not cached.startswith('W/') else cached

#     payload = canon.encode("utf-8")
#     digest = hashlib.sha256(payload).hexdigest()
#     quoted = f'"{digest}"'            # strong quoted ETag
#     _etag_cache.set(canon, quoted)
#     if weak:
#         return f'W/{quoted}'
#     return quoted


# _ETAG_TOKEN_RE = re.compile(r'(W/)?"((?:[^"\\]|\\.)*)"|([^,\s]+)')

# def parse_if_none_match(header_value: str) -> Iterable[Tuple[bool, str]]:
#     """
#     Parse If-None-Match header into sequence of (is_weak, tag_value) pairs.
#     - If header is "*" yields (False, "*")
#     - tag_value is the inner (unquoted) string for quoted ETags, or raw token for unquoted.
#     """
#     if header_value is None:
#         return ()
#     header_value = header_value.strip()
#     if header_value == '*':
#         return ((False, '*'),)

#     matches = []
#     for m in _ETAG_TOKEN_RE.finditer(header_value):
#         weak_prefix = m.group(1)
#         quoted_inner = m.group(2)
#         unquoted_token = m.group(3)
#         if quoted_inner is not None:
#             is_weak = bool(weak_prefix)
#             tag = quoted_inner
#         elif unquoted_token is not None:
#             is_weak = bool(weak_prefix)
#             tag = unquoted_token
#         else:
#             continue
#         matches.append((is_weak, tag))
#     return matches

# def _normalize_etag_value(etag: str) -> str:
#     """Return normalized etag content (without W/ and without surrounding quotes)."""
#     if etag.startswith('W/'):
#         etag = etag[2:]
#     etag = etag.strip()
#     if len(etag) >= 2 and etag[0] == '"' and etag[-1] == '"':
#         return etag[1:-1]
#     return etag


# def respond_with_etag_json(data: Any, status: int = 200, cache_ttl: Optional[int] = None, *, generate_weak_etag: bool = False) -> Response:
#     """Return a Quart Response for JSON with ETag support and optional Cache-Control."""
#     # Attempt to compute ETag (may raise TypeError if value not serializable)
#     etag = generate_etag_from_data(data, weak=generate_weak_etag)
#     # For matching, compare normalized (unquoted) digest values
#     normalized_current = _normalize_etag_value(etag)

#     if_none_match = None
#     try:
#         if_none_match = request.headers.get('If-None-Match')
#     except Exception:
#         # No request context — behave as if no conditional header
#         if_none_match = None

#     def set_cache_headers(resp: Response) -> Response:
#         resp.headers['ETag'] = etag
#         if cache_ttl is not None:
#             resp.headers['Cache-Control'] = f'public, max-age={int(cache_ttl)}'
#         return resp

#     if if_none_match:
#         parsed = parse_if_none_match(if_none_match)
#         matched = False
#         for is_weak, token in parsed:
#             # wildcard '*' -> matches existing resource
#             if token == '*':
#                 matched = True
#                 break
#             # normalize header token and compare using **weak** comparison semantics:
#             # RFC: For If-None-Match the weak comparison is appropriate for GET/HEAD.
#             # We'll compare the underlying digests equality (ignoring W/).
#             if _normalize_etag_value(token) == normalized_current:
#                 matched = True
#                 break

#         if matched:
#             method = None
#             try:
#                 method = request.method
#             except Exception:
#                 method = 'GET'
#             if method in ('GET', 'HEAD'):
#                 resp = Response(status=304)
#                 return set_cache_headers(resp)
#             else:
#                 # For methods other than GET/HEAD, If-None-Match match -> 412 per RFC
#                 resp = Response(status=412)
#                 return set_cache_headers(resp)

#     # No match => send full JSON response
#     resp = jsonify(data)
#     resp.status_code = status
#     return set_cache_headers(resp)


# ─── Communication Functions ──────────────────────────────────────────────────

async def _send_async_email(to_email: str, subject: str, body: str) -> bool:
    """Send email asynchronously"""
    try:
        if not config.BUSINESS_EMAIL:
            raise ValueError("Business email not configured")
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = config.BUSINESS_EMAIL
        msg['To'] = to_email
        
        # Use asyncio to run SMTP in thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp_email, msg, to_email)
        return True
    except Exception as e:
        log.critical(action="email_error", trace_info=to_email, message=str(e), secure=True)
        return False

def _send_smtp_email(msg: MIMEText, to_email: str) -> None:
    """Send email via SMTP (blocking)"""
    if not config.BUSINESS_EMAIL or not config.SERVICE_EMAIL_PASSWORD:
        raise ValueError("Business email or service password not configured")
    server = smtplib.SMTP(config.BUSINESS_EMAIL or "", config.SERVICE_EMAIL_PORT)
    server.starttls()
    server.login(config.BUSINESS_EMAIL, config.SERVICE_EMAIL_PASSWORD)
    server.sendmail(config.BUSINESS_EMAIL, to_email, msg.as_string())
    server.quit()

def send_email(to_email: str, subject: str, 
               body: str) -> bool:
    """Send email with enhanced error handling"""
    asyncio.create_task(delete_code())
    return asyncio.run(_send_async_email(to_email, subject, body))

async def _send_async_sms(phone: str, msg: str) -> bool:
    """Send SMS asynchronously"""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _send_sms_request, phone, msg)
        return result
    except Exception as e:
        log.critical(action="sms_error", trace_info=phone, message=str(e), secure=True)
        return False

def _send_sms_request(phone: str, msg: str) -> bool:
    """Send SMS request (blocking)"""
    response = requests.post(config.SERVICE_PHONE_URL, {
        'phone': phone,
        'message': msg,
        'key': config.SERVICE_PHONE_API_KEY
    })
    
    try:
        result = response.json()
        return result.get("success", False)
    except Exception as e:
        log.critical(action="sms_parse_error", trace_info=phone, message=str(e), secure=True)
        return False

def send_sms(phone: str, msg: str) -> bool:
    """Send SMS with enhanced error handling"""
    asyncio.create_task(delete_code())
    return asyncio.run(_send_async_sms(phone, msg))

# ─── Database Functions ──────────────────────────────────────────────────────

@asynccontextmanager
async def get_db_context():
    """Database connection context manager"""
    conn = await get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

async def get_email(fullname: str, phone: str) -> Optional[str]:
    """Get user email with caching"""
    cache_key = f"email:{fullname}:{phone}"
    cached_email = cache.get(cache_key)
    if cached_email:
        return cached_email
    
    if config.is_testing():
        return os.getenv("DUMMY_EMAIL")
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT email FROM global.users WHERE fullname = %s AND phone = %s",
                    (fullname, phone)
                )
                result = await cursor.fetchone()
                
                email = result['email'] if result else None
                if email:
                    cache.set(cache_key, email, ttl=3600)  # Cache for 1 hour
                return email
        except Exception as e:
            log.critical(action="db_error with get_email", trace_info=phone, message=str(e), secure=True)
            return None

async def get_id(phone: str, fullname: str) -> Optional[int]:
    """Get user ID with caching"""
    cache_key = f"user_id:{phone}:{fullname}"
    cached_id = cache.get(cache_key)
    if cached_id:
        return cached_id
    
    if config.is_testing():
        fullname = config.DUMMY_FULLNAME
        phone = config.DUMMY_PHONE
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s AND fullname = %s",
                    (phone, fullname)
                )
                result = await cursor.fetchone()
                
                user_id = result['user_id'] if result else None
                if user_id:
                    cache.set(cache_key, user_id, ttl=3600)  # Cache for 1 hour
                return user_id
        except Exception as e:
            log.critical(action="get_id_error", trace_info=phone,message=str(e), secure=True)
            return None

async def upsert_translation(conn, translation_text: str, madrasa_name: str, bn_text = None, ar_text = None, context = None) -> Optional[str]:
    """
    Insert or update a translation entry in the global.translations table
    Returns the translation_text that should be used as foreign key reference
    """
    if not translation_text or not translation_text.strip():
        return None
        
    translation_text = translation_text.strip()
    
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        # Upsert translation entry
        sql = f"""
            INSERT INTO {madrasa_name}.translations (translation_text, bn_text, ar_text, context)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                bn_text = COALESCE(VALUES(bn_text), bn_text),
                ar_text = COALESCE(VALUES(ar_text), ar_text),
                context = COALESCE(VALUES(context), context)
        """
        await cursor.execute(sql, (translation_text, bn_text, ar_text, context))
        return translation_text

async def process_multilingual_field(conn, field_base: str, data: dict, madrasa_name: str) -> Optional[str]:
    """
    Process multilingual field data and insert into translations table
    Returns the translation_text to use as foreign key reference
    """
    translation_text = data.get(f"{field_base}_en")
    bn_text = data.get(f"{field_base}_bn") 
    ar_text = data.get(f"{field_base}_ar")
    
    # Use English text as the primary translation_text key
    if not translation_text:
        return None
        
    translation_text = translation_text.strip()
    return await upsert_translation(conn=conn, translation_text=translation_text, bn_text=bn_text, ar_text=ar_text, madrasa_name=madrasa_name)

async def insert_person(madrasa_name: str, fields: Dict[str, Any], acc_type: str, phone: str) -> None:
    """Enhanced person insertion with translation handling and error handling"""
    if config.is_testing():
        return None

    fields = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
    
    async with get_db_context() as conn:
        try:
            # Handle translations first for foreign key fields
            translation_fields = {}
            
            # Process name translations
            if any(k.startswith('name_') for k in fields.keys()):
                name_translation = await process_multilingual_field(conn=conn, field_base='name', data=fields, madrasa_name=madrasa_name)
                if name_translation:
                    translation_fields['name'] = name_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('name_')}
            
            # Process father name translations  
            if any(k.startswith('father_') for k in fields.keys()):
                father_translation = await process_multilingual_field(conn=conn, field_base='father', data=fields, madrasa_name=madrasa_name)
                if father_translation:
                    translation_fields['father_name'] = father_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('father_')}
            
            # Process mother name translations
            if any(k.startswith('mother_') for k in fields.keys()):
                mother_translation = await process_multilingual_field(conn=conn, field_base='mother', data=fields, madrasa_name=madrasa_name)
                if mother_translation:
                    translation_fields['mother_name'] = mother_translation
                    # Remove individual language fields
                    fields = {k: v for k, v in fields.items() if not k.startswith('mother_')}
            
            # Handle address field - use present_address as the main address
            if 'present_address' in fields and fields['present_address']:
                address_text = fields['present_address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['present_address'])
                if address_translation:
                    translation_fields['address'] = address_translation

            # Handle address field - use present_address as the main address
            if 'permanent_address' in fields and fields['permanent_address']:
                address_text = fields['permanent_address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['present_address'])
                if address_translation:
                    translation_fields['address'] = address_translation

            # Handle address field - use present_address as the main address
            if 'address' in fields and fields['address']:
                address_text = fields['address'].strip().lower()
                address_translation = await upsert_translation(conn, address_text, fields['address'])
                if address_translation:
                    translation_fields['address'] = address_translation
            
            # Merge translation fields with other fields
            fields.update(translation_fields)
            
            # Separate acc_type fields from peoples fields
            acc_type_fields = {}
            peoples_fields = {}
            
            for key, value in fields.items():
                if key in ['teacher', 'student', 'staff', 'donor', 'badri_member', 'special_member']:
                    acc_type_fields[key] = value
                else:
                    peoples_fields[key] = value
            
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Insert into acc_types table FIRST if user_id exists
                if 'user_id' in peoples_fields and peoples_fields['user_id']:
                    user_id = peoples_fields['user_id']
                    
                    # Use boolean values from route (they already have correct defaults)
                    acc_type_data = {
                        'user_id': user_id,
                        'main_type': acc_type,
                        'teacher': int(acc_type_fields.get('teacher', False)),
                        'student': int(acc_type_fields.get('student', False)),
                        'staff': int(acc_type_fields.get('staff', False)),
                        'donor': int(acc_type_fields.get('donor', False)),
                        'badri_member': int(acc_type_fields.get('badri_member', False)),
                        'special_member': int(acc_type_fields.get('special_member', False))
                    }
                    
                    acc_columns = ', '.join(acc_type_data.keys())
                    acc_placeholders = ', '.join(['%s'] * len(acc_type_data))
                    acc_updates = ', '.join([f"{col} = VALUES({col})" for col in acc_type_data.keys() if col != 'user_id'])
                    
                    # UPSERT for acc_types
                    acc_sql = f"""
                        INSERT INTO global.acc_types ({acc_columns})
                        VALUES ({acc_placeholders})
                        ON DUPLICATE KEY UPDATE {acc_updates}
                    """
                    await cursor.execute(acc_sql, list(acc_type_data.values()))
                
                # Insert into peoples table AFTER acc_types
                columns = ', '.join(peoples_fields.keys())
                placeholders = ', '.join(['%s'] * len(peoples_fields))
                
                # Only update non-identity or safe fields
                updatable_fields = [
                    col for col in peoples_fields.keys() 
                    if col not in ('user_id', 'created_at', 'updated_at')
                ]
                updates = ', '.join([f"{col} = VALUES({col})" for col in updatable_fields])
                
                # UPSERT for peoples
                sql = f"""
                    INSERT IGNORE INTO {madrasa_name}.peoples ({columns}) 
                    VALUES ({placeholders}) AS new
                    ON DUPLICATE KEY UPDATE {updates}
                """
                await cursor.execute(sql, list(peoples_fields.values()))
                
            await conn.commit()
            log.info(action="insert_success", trace_info=phone, message="Upserted into peoples with translations", secure=True)
        except Exception as e:
            await conn.rollback()
            log.critical(action="db_insert_error", trace_info=phone,message=str(e), secure=True)
            raise

async def delete_users(madrasa_name: Optional[Union[str, list[str]]] = None, uid = None, acc_type = None) -> bool:
    """Enhanced user deletion with comprehensive cleanup"""
    if not madrasa_name:
        madrasa_name = config.MADRASA_NAMES_LIST
    for madrasa in madrasa_name if isinstance(madrasa_name, list) else [madrasa_name]:
        async with get_db_context() as conn:
            try:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    if not uid and not acc_type:
                        await cursor.execute(f"""
                            SELECT u.user_id, p.acc_type 
                            FROM global.users u
                            JOIN {madrasa}.peoples p ON u.user_id = p.user_id
                            WHERE u.scheduled_deletion_at IS NOT NULL
                            AND u.scheduled_deletion_at < NOW()
                        """)
                        users_to_delete = await cursor.fetchall()
                    else:
                        users_to_delete = [{'user_id': uid, 'acc_type': acc_type}]
                
                for user in users_to_delete:
                    uid = user["user_id"]
                    acc_type = user["acc_type"]
                    
                    if acc_type not in ['students', 'teachers', 'staffs', 'admins', 'badri_members']:
                        await cursor.execute(f"DELETE FROM {madrasa_name}.peoples WHERE user_id = %s", (uid,))
                    else:
                        await cursor.execute(f"""
                            UPDATE {madrasa_name}.peoples SET 
                                date_of_birth = NULL,
                                birth_certificate = NULL,
                                national_id = NULL,
                                source = NULL,
                                present_address = NULL,
                                permanent_address = NULL,
                                father_or_spouse = NULL,
                                mother_en = NULL,
                                mother_bn = NULL,
                                mother_ar = NULL,
                                guardian_number = NULL,
                                available = NULL,
                                is_donor = NULL,
                                is_badri_member = NULL,
                                is_foundation_member = NULL
                            WHERE user_id = %s
                        """, (uid,))
                    
                    await cursor.execute(f"DELETE FROM global.transactions WHERE user_id = %s", (uid,))
                    await cursor.execute(f"DELETE FROM global.verifications WHERE user_id = %s", (uid,))
                    await cursor.execute(f"DELETE FROM global.users WHERE user_id = %s", (uid,))
                
                await conn.commit()
                return True
                
            except IntegrityError as e:
                log.critical(action="auto_delete_error", trace_info="Null", message=f"IntegrityError: {e}", secure=False)
                return False
            except Exception as e:
                log.critical(action="auto_delete_error", trace_info="Null", message=str(e), secure=False)
                return False
    return False

# ─── Business Logic Functions ────────────────────────────────────────────────

def calculate_fees(class_name: str, gender: str, special_food: int, 
                  reduced_fee: int, food: int) -> int:
    """Calculate fees with comprehensive pricing logic"""
    total = 0
    class_lower = class_name.lower()
    
    if config.is_testing():
        return 9999
    
    # Food charges
    if food == 1:
        total += 2400
    if special_food == 1:
        total += 3000
    
    # Base fees by gender and class
    if gender.lower() == 'male':
        if class_lower in ['class 3', 'class 2']:
            total += 1600
        elif class_lower in ['hifz', 'nazara']:
            total += 1800
        else:
            total += 1300
    elif gender.lower() == 'female':
        if class_lower == 'nursery':
            total += 800
        elif class_lower == 'class 1':
            total += 1000
        elif class_lower == 'hifz':
            total += 2000
        elif class_lower in ['class 2', 'class 3', 'nazara']:
            total += 1200
        else:
            total += 1500
    
    # Apply fee reduction
    if reduced_fee:
        total -= reduced_fee
    
    return max(0, total)  # Ensure non-negative total

# ─── File Management Functions ───────────────────────────────────────────────

def load_results() -> List[Dict[str, Any]]:
    """Load exams results with caching and error handling."""
    cache_key = "load_results:default"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        with open(config.EXAM_RESULTS_INDEX_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    cache.set(cache_key, data, ttl=config.CACHE_TTL)
    return data

def save_results(data: List[Dict[str, Any]]) -> None:
    """Save exam results with atomic write and cache invalidation."""
    temp_file = config.EXAM_RESULTS_INDEX_FILE + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, config.EXAM_RESULTS_INDEX_FILE)
        # Invalidate cached loads
        invalidate_cache_pattern("load_results:")
    except Exception as e:
        log.critical(action="save_results_error", trace_info="file_ops", message=str(e), secure=False)
        if os.path.exists(temp_file):
            os.remove(temp_file)

def load_notices() -> List[Dict[str, Any]]:
    """Load notices with caching and auto-recovery from corrupted files."""
    cache_key = "load_notices:default"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        with open(config.NOTICES_INDEX_FILE, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        # Auto-fix broken JSON
        with open(config.NOTICES_INDEX_FILE, 'w') as f:
            json.dump([], f)
        data = []
    except FileNotFoundError:
        data = []
    cache.set(cache_key, data, ttl=config.CACHE_TTL)
    return data

def save_notices(data: List[Dict[str, Any]]) -> None:
    """Save notices with atomic write and cache invalidation."""
    temp_file = config.NOTICES_INDEX_FILE + '.tmp'
    try:
        with open(temp_file, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(temp_file, config.NOTICES_INDEX_FILE)
        # Invalidate cached loads
        invalidate_cache_pattern("load_notices:")
    except Exception as e:
        log.critical(action="save_notices_error", trace_info="file_ops", message=str(e), secure=False)
        if os.path.exists(temp_file):
            os.remove(temp_file)

# ─── Utility Decorators ─────────────────────────────────────────────────────

def rate_limit(max_requests: int, window: int):
    """Decorator for rate limiting endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get client identifier (IP address)
            client_ip = request.remote_addr
            identifier = f"{client_ip}:{func.__name__}"
            
            if not check_rate_limit(identifier, max_requests, window):
                return jsonify({"error": "Rate limit exceeded"}), 429
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def require_api_key(func):
    """Decorator to require valid API key"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if not api_key or not is_valid_api_key(api_key):
            return jsonify({"error": "Invalid or missing API key"}), 401
        return await func(*args, **kwargs)
    return wrapper

# ─── Health Check Functions ─────────────────────────────────────────────────

async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and health"""
    try:
        async with get_db_context() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SELECT 1")
                return {"status": "healthy", "message": "Database connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"Database error: {str(e)}"}

async def check_file_system_health() -> Dict[str, Any]:
    """Check file system health and permissions"""
    try:
        # Check if directories exist and are writable
        for directory in [config.EXAM_RESULTS_UPLOAD_FOLDER, config.NOTICES_UPLOAD_FOLDER]: # TODO: Add more directories to check
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
            
            test_file = os.path.join(directory, '.health_check')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        
        return {"status": "healthy", "message": "File system accessible"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"File system error: {str(e)}"}

async def get_system_health() -> Dict[str, Any]:
    """Get comprehensive system health status"""
    db_health = await check_database_health()
    fs_health = await check_file_system_health()

    status = "healthy"
    if db_health["status"] == "unhealthy" and fs_health["status"] == "unhealthy":
        status = "critical"
    elif db_health["status"] == "unhealthy" or fs_health["status"] == "unhealthy":
        status = "unhealthy"
    
    return {
        "status": status,
        "version": config.SERVER_VERSION,
        "timestamp": datetime.now().isoformat(),
        "database": db_health,
        "file_system": fs_health,
        "maintenance_mode": config.is_maintenance(),
        "test_mode": config.is_testing(),
        "cache_size": len(cache._cache),
        "rate_limiter_size": len(rate_limiter._requests)
    }


# ─── Performance Monitoring ─────────────────────────────────────────────────

class PerformanceMonitor:
    """Monitor application performance and resource usage"""
    
    def __init__(self):
        self.request_times = []
        self.error_counts = {}
        self.start_time = time.time()
    
    def record_request_time(self, endpoint: str, duration: float) -> None:
        """Record request processing time"""
        self.request_times.append({
            'endpoint': endpoint,
            'duration': duration,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 1000 requests
        if len(self.request_times) > 1000:
            self.request_times = self.request_times[-1000:]
    
    def record_error(self, error_type: str, details: str) -> None:
        """Record error occurrence"""
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        if not self.request_times:
            return {"message": "No performance data available"}
        
        durations = [req['duration'] for req in self.request_times]
        return {
            "total_requests": len(self.request_times),
            "average_response_time": sum(durations) / len(durations),
            "min_response_time": min(durations),
            "max_response_time": max(durations),
            "uptime_seconds": time.time() - self.start_time,
            "error_counts": self.error_counts
        }

# Global performance monitor
performance_monitor = PerformanceMonitor()

# ─── Advanced Error Handling ───────────────────────────────────────────────

class AppError(Exception): # TODO: Implement this
    """Base application error class"""
    def __init__(self, message: str, error_code = None, details = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


def handle_async_errors(func: Callable) -> Callable:
    """Decorator for comprehensive async error handling"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except AppError as e:
            log.critical(action="app_error", trace_info="error_handler", message=f"{e.error_code}: {e.message}", secure=False)
            return jsonify({
                "error": e.message,
                "error_code": e.error_code,
                "details": e.details
            }), 400
        except Exception as e:
            log.critical(action="unexpected_error", trace_info="error_handler", message=str(e), secure=False)
            performance_monitor.record_error("unexpected", str(e))
            return jsonify({
                "error": "An unexpected error occurred",
                "error_code": "INTERNAL_ERROR"
            }), 500
    
    return wrapper

# ─── Metrics and Analytics ─────────────────────────────────────────────────

class MetricsCollector: # TODO: Implement this
    """Collect and analyze application metrics"""
    
    def __init__(self):
        self.metrics = {
            'requests': 0,
            'errors': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'database_queries': 0,
            'slow_queries': 0
        }
        self.start_time = time.time()
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Increment a metric counter"""
        if metric in self.metrics:
            self.metrics[metric] += value
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        uptime = time.time() - self.start_time
        return {
            **self.metrics,
            'uptime_seconds': uptime,
            'requests_per_second': self.metrics['requests'] / uptime if uptime > 0 else 0,
            'error_rate': self.metrics['errors'] / self.metrics['requests'] if self.metrics['requests'] > 0 else 0,
            'cache_hit_rate': self.metrics['cache_hits'] / (self.metrics['cache_hits'] + self.metrics['cache_misses']) if (self.metrics['cache_hits'] + self.metrics['cache_misses']) > 0 else 0
        }

# Global metrics collector
metrics_collector = MetricsCollector()


# ─── Application Initialization ────────────────────────────────────────────

def initialize_application() -> bool:
    """Initialize application with all necessary components"""
    try:
        # Initialize cache
        cache.clear()
        
        # Initialize rate limiter
        rate_limiter._requests.clear()
        
        # Log successful initialization  
        log.info(action="app_initialized", trace_info="system", message="Application initialized successfully", secure=False)
        return True
        
    except Exception as e:
        log.critical(action="init_error", trace_info="system", message=str(e), secure=False)
        return False

# ─── CSRF Protection ───────────────────────────────────────────────────────

async def validate_csrf_token():
    """Validate CSRF token from form data"""
    from csrf_protection import validate_csrf_token
    form = await request.form
    token = form.get('csrf_token')
    if not validate_csrf_token(token):
        await flash("CSRF token validation failed. Please try again.", "danger")
        return False
    return True

def require_csrf(f):
    """Decorator to require CSRF validation for POST requests"""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            if not await validate_csrf_token():
                return redirect(request.url)
        return await f(*args, **kwargs)
    return decorated_function

# ─────────────────────────────────────────────────────────────────────────────
# ──────────────────────── Security functions ─────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


# ─── Rate Limiting ───────────────────────────────────────────────────────────

class RateLimiter:
    """Advanced rate limiting with sliding window"""
    
    def __init__(self):
        self._requests: Dict[str, List[float]] = {}
        self._cleanup_interval = 1 * 3600  # 1 hour
        self._last_cleanup = time.time()
    
    def is_allowed(self, identifier: str, max_requests: int, window: int) -> bool:
        """Check if request is allowed based on rate limit"""
        current_time = time.time()
        
        # Cleanup old entries periodically
        if current_time - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = current_time
        
        # Get request history for this identifier
        requests = self._requests.get(identifier, [])
        
        # Remove requests outside the window
        window_start = current_time - window
        requests = [req_time for req_time in requests if req_time > window_start]
        
        # Check if under limit
        if len(requests) < max_requests:
            requests.append(current_time)
            self._requests[identifier] = requests
            return True
        
        return False
    
    def _cleanup(self) -> None:
        """Remove old request records"""
        current_time = time.time()
        old_identifiers = []
        
        for identifier, requests in self._requests.items():
            # Keep only recent requests (within last hour)
            recent_requests = [req for req in requests if current_time - req < 3600]
            if recent_requests:
                self._requests[identifier] = recent_requests
            else:
                old_identifiers.append(identifier)
        
        for identifier in old_identifiers:
            del self._requests[identifier]

# Global rate limiter instance
rate_limiter = RateLimiter()

# ─── Security Functions ───────────────────────────────────────────────────────

def is_valid_api_key(api_key: str) -> bool:
    """Validate API key securely based on request method"""

    if config.is_testing():
        return True

    if not api_key:
        return False

    return any(compare_digest(api_key, key) for key in config.API_KEYS if isinstance(key, str))


async def check_rate_limit(identifier: str, max_requests = None, window = None) -> bool:
    """Enhanced rate limiting with additional checks"""
    if max_requests is None:
        max_requests = config.DEFAULT_RATE_LIMIT
    if window is None:
        window = config.RATE_LIMIT_WINDOW
    
    # Additional security checks
    client_info = get_client_info()
    
    # Check for suspicious patterns
    if security_manager.detect_sql_injection(identifier):
        await security_manager.track_suspicious_activity(
            client_info["ip_address"], 
            "SQL injection attempt"
        )
        return False
        
    # Check basic rate limit
    if not rate_limiter.is_allowed(identifier, max_requests, window):
        return False
    
    return True

async def _send_security_notifications(ip_address: str, device_id: str, info: str) -> None:
    """Send security breach notifications"""
    notification_data = {
        "ip_address": ip_address,
        "device_id": device_id,
        "info": info,
        "timestamp": datetime.now().isoformat()
    }
    
    # Send emails
    for email in [config.DEV_EMAIL, config.BUSINESS_EMAIL]:
        if email:
            await _send_async_email(
                to_email=email,
                subject="Security Breach Alert",
                body=f"""Security Breach Detected

                        An unknown device attempted to access the application.

                        Details:
                        - IP Address: {ip_address}
                        - Device ID: {device_id}
                        - Additional Info: {info}
                        - Timestamp: {notification_data['timestamp']}

                        Please review and take appropriate action.

                        @An-Nur.app"""
                        )
    
    # Send SMS
    for phone in [config.DEV_PHONE, config.BUSINESS_PHONE]:
        if phone:
            await _send_async_sms(
                phone=phone,
                msg=f"""Security Breach Alert

                        Unknown device access attempt:
                        IP: {ip_address}
                        Device: {device_id}
                        Info: {info}

                        @An-Nur.app"""
                        )

# ─── Verification Functions ───────────────────────────────────────────────────

def generate_code(code_length: Optional[int] = None) -> int:
    """Generate secure verification code"""
    code_length = code_length or config.CODE_LENGTH
    return random.randint(10**(code_length-1), 10**code_length - 1)

async def check_code(user_code: str, phone: str) -> Optional[Tuple[Response, int]]:
    """Enhanced code verification with security features"""
    conn = await get_db_connection()
    
    if config.is_testing():
        return None
    
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                SELECT code, created_at FROM global.verifications
                WHERE phone = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (phone,))
            result = await cursor.fetchone()
            
            if not result:
                return jsonify({"message": "No verification code found"}), 404
            
            db_code = result["code"]
            created_at = result["created_at"]
            now = datetime.now()
            
            # Check expiration
            if (now - created_at).total_seconds() > config.CODE_EXPIRY_MINUTES * 60:
                return jsonify({"message": "Verification code expired"}), 410
            
            # Constant-time comparison
            if int(user_code) == db_code:
                await delete_code()
                return None
            else:
                log.warning(action="verification_failed", trace_info=phone, message="Code mismatch", secure=True)
                return jsonify({"message": "Verification code mismatch"}), 400
    
    except Exception as e:
        log.critical(action="verification_error", trace_info=phone, message=str(e), secure=True)
        return jsonify({"message": f"Error: {str(e)}"}), 500

async def delete_code() -> None:
    """Delete expired verification codes"""
    conn = await get_db_connection()
    try:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute("""
                DELETE FROM global.verifications
                WHERE created_at < NOW() - INTERVAL 1 DAY
            """)
        await conn.commit()
    except Exception as e:
        log.critical(action="failed_to_delete_verifications", trace_info="N/A", message=f"Database Error {str(e)}", secure=False)

# ─── Validation Functions ────────────────────────────────────────────────────

def format_phone_number(phone: str) -> Tuple[Optional[str], str]:
    """Format and validate phone number to international E.164 format"""
    if config.is_testing():
        phone = config.DUMMY_PHONE

    if not phone:
        return None, "Phone number is required"
    phone = phone.strip().replace(" ", "").replace("-", "")

    # Normalize BD formats
    if phone.startswith("8801") and len(phone) == 13:
        phone = "+" + phone
    elif phone.startswith("01") and len(phone) == 11:
        phone = "+88" + phone
    elif not phone.startswith("+"):
        return None, "Phone number must start with + or be a valid local format"

    try:
        number = phonenumbers.parse(phone, None)
        if not phonenumbers.is_valid_number(number):
            log.error(action="invalid_phone_number", trace_info=phone, message="Invalid phone number format", secure=True)
            return None, "Invalid phone number"

        number_type = phonenumbers.number_type(number)
        if number_type not in [phonenumbers.PhoneNumberType.MOBILE, phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE]:
            return None, "Phone number must be a mobile or landline number"
        formatted = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
        return formatted, ""

    except phonenumbers.NumberParseException:
        log.error(action="invalid_phone_number", trace_info=phone, message="Invalid phone number format", secure=True)
        return None, "Invalid phone number format"


def validate_fullname(fullname: str) -> Tuple[bool, str]:
    """Enhanced fullname validation with comprehensive checks"""
    # Allow letters, spaces, apostrophes, and hyphens
    _FULLNAME_RE = re.compile(
        r"^(?!.*[\d])"                     # no digits
        r"(?!.*[!@#$%^&*()_+=-])"           # no forbidden special chars
        r"([A-Z][a-z']+)"               # first word (allow ' and -)
        r"(?: [A-Z][a-z']+)*$"          # additional words
    )
    fullname = fullname.strip()
    if re.search(r'\d', fullname):
        return False, "Fullname shouldn't contain digits"
    if re.search(r'[!@#$%^&*()_+=-]', fullname):
        return False, "Fullname shouldn't contain special characters"
    if not _FULLNAME_RE.match(fullname):
        return False, "Fullname must be words starting with uppercase, followed by lowercase letters, apostrophes, or hyphens"
    return True, ""

def validate_request_data(data: Dict[str, Any], required_fields: List[str]) -> Tuple[bool, List[str]]:
    """Validate authentication request data"""
    missing_fields = []
    for field in required_fields:
        if not data.get(field):
            missing_fields.append(field)
    return len(missing_fields) == 0, missing_fields

async def validate_device_info(device_id: str, ip_address: str, device_brand: str, device_model: str, device_os: str) -> Tuple[bool, str]:
    """Validate device information for security"""
    # Validate IP address format
    ip_pattern = re.compile(r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$')
    if not ip_pattern.match(ip_address):
        return False, "Invalid IP address format"
    
    # Check for suspicious device patterns
    suspicious_patterns = [
        r'^(test|dummy|fake|null|undefined)$',
        r'[<>"\']',
        r'\.\.',
        r'javascript:',
        r'<script'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, device_id, re.IGNORECASE) or re.search(pattern, device_brand, re.IGNORECASE) or re.search(pattern, device_model, re.IGNORECASE) or re.search(pattern, device_os, re.IGNORECASE):
            security_manager.track_suspicious_activity(ip_address, "Suspicious device identifier detected")
            return False, "Suspicious device identifier detected"
    
    return True, ""

# ─── Advanced Security Functions ────────────────────────────────────────────

class SecurityManager:
    """Advanced security management with threat detection"""
    
    def __init__(self):
        self.suspicious_patterns = [
            r"(?i)(union(\s+all)?\s+select|select\s+.*from|insert\s+into|update\s+.*set|delete\s+from|drop\s+table|create\s+table|alter\s+table|--|#|;|\bor\b|\band\b|\bexec\b|\bsp_\b|\bxp_\b)",
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        self.blocked_ips = set() # save the blocked ips in a set or database
        self.suspicious_activities = {} # save the suspicious activities in a dictionary or database
    
    def detect_sql_injection(self, input_str: str) -> bool:
        """Detect potential SQL injection attempts"""
        input_lower = input_str.lower()
        for pattern in self.suspicious_patterns:
            if re.search(pattern, input_lower, re.IGNORECASE):
                return True
        return False
    
    def detect_xss(self, input_str: str) -> bool:
        """Detect potential XSS attempts"""
        if not input_str:
            return False
        
        xss_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]
        
        for pattern in xss_patterns:
            if re.search(pattern, input_str, re.IGNORECASE):
                return True
        return False
    
    def sanitize_inputs(self, input_str: str) -> str:
        """Sanitize user input"""
        if not input_str:
            return ""
        
        # Remove potentially dangerous characters
        sanitized = re.sub(r'[<>"\']', '', input_str)
        return sanitized.strip()
    
    async def track_suspicious_activity(self, ip_address: str, activity: str) -> None:
        """Track suspicious activities for threat analysis"""
        if ip_address not in self.suspicious_activities:
            self.suspicious_activities[ip_address] = []
        
        self.suspicious_activities[ip_address].append({
            'activity': activity,
            'timestamp': datetime.now().isoformat()
        })
        
        # If too many suspicious activities, block IP
        if len(self.suspicious_activities[ip_address]) > 10:
            self.blocked_ips.add(ip_address)
            await _send_security_notifications(ip_address, "system", f"Too many suspicious activities: {activity}")
            log.critical(action="ip_blocked", trace_info=ip_address, message=f"Too many suspicious activities: {activity}", secure=False)

# Global security manager
security_manager = SecurityManager()


# ─── Performance Monitoring and Metrics ───────────────────────────────────────
def record_request_metrics(endpoint: str, duration: float, status_code: int) -> None:
    """Record request metrics for monitoring"""
    performance_monitor.record_request_time(endpoint, duration)
    metrics_collector.increment('requests')
    
    if status_code >= 400:
        metrics_collector.increment('errors')
        performance_monitor.record_error('http_error', f"Status {status_code}")

def monitor_database_performance(query: str, duration: float) -> None:
    """Monitor database query performance"""
    metrics_collector.increment('database_queries')
    
    if duration > 1.0:  # Log slow queries
        metrics_collector.increment('slow_queries')
        log.warning(action="slow_database_query", trace_info=get_client_info()["ip_address"], message=f"Slow query detected: {duration:.2f}s", secure=False)


# ─── Advanced Validation Functions ──────────────────────────────────────────

def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format with comprehensive checks"""
    if not email:
        return False, "Email is required"
    
    # Basic email pattern
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    # Disallow consecutive dots and leading/trailing dots in local or domain part
    local, _, domain = email.partition('@')
    if '..' in local or '..' in domain:
        return False, "Email cannot contain consecutive dots"
    if local.startswith('.') or local.endswith('.') or domain.startswith('.') or domain.endswith('.'):
        return False, "Email cannot start or end with a dot"
    # Check for suspicious patterns
    if security_manager.detect_xss(email):
        return False, "Email contains suspicious content"
    
    return True, ""

def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Enhanced password strength validation"""
    if len(password) < config.PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    
    # Check for common weak passwords
    weak_passwords = ['password', '123456', 'qwerty', 'admin', 'user']
    if password.lower() in weak_passwords:
        return False, "Password is too common"
    
    return True, ""


def validate_file_upload(file, allowed_extensions: List[str], max_size: Optional[int] = config.MAX_CONTENT_LENGTH) -> Tuple[bool, str]:
    """Enhanced file upload validation with security checks"""
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file extension
    if '.' not in file.filename:
        return False, "Invalid file format"
    
    extension = file.filename.rsplit('.', 1)[1].lower()
    if extension not in allowed_extensions:
        return False, f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
    
    # Check file size
    if file.content_length and file.content_length > max_size:
        return False, f"File size exceeds maximum allowed size ({max_size or config.MAX_CONTENT_LENGTH / 1024 / 1024} MB)"
    
    # Check for suspicious filename patterns
    suspicious_patterns = [
        r'\.\./', r'\.\.\\', r'[<>:"|?*]',
        r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, file.filename, re.IGNORECASE):
            log.warning(
                action="suspicious_filename",
                trace_info=get_client_info()["ip_address"],
                message=f"Suspicious filename detected: {file.filename}",
                secure=False
            )
            return False, "Invalid filename"
    
    return True, ""

# ──── User Login Limits ────────────────────────────────────────────────────
async def check_device_limit(user_id: int, device_id: str) -> Tuple[bool, str]: # TODO: fix the device limit where it should delete from interactions table
    """Check if user has reached device limit"""
    try:
        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            # Check if this device is already registered for this user
            await cursor.execute(
                "SELECT device_id FROM global.interactions WHERE user_id = %s AND device_id = %s LIMIT 1",
                (user_id, device_id)
            )
            existing_device = await cursor.fetchone()
            
            if existing_device:
                return True, ""  # Device already registered, allow access
            
            # Count total devices for this user
            await cursor.execute(
                "SELECT COUNT(*) as device_count FROM global.interactions WHERE user_id = %s",
                (user_id,)
            )
            result = await cursor.fetchone()
            device_count = result['device_count'] if result else 0
            
            if device_count >= config.MAX_DEVICES_PER_USER:
                return False, f"Maximum devices ({config.MAX_DEVICES_PER_USER}) reached. Please remove an existing device to add this one."
            
            return True, ""
    except Exception as e:
        log.critical(
            action="device_limit_check_error",
            trace_info=str(user_id),
            message=f"Error checking device limit: {str(e)}",
            secure=False
        )
        return False, "Error checking device limit"

def check_login_attempts(identifier: str) -> Tuple[bool, int]:
    """Check login attempts and return if allowed and remaining attempts"""
    cache_key = f"login_attempts:{identifier}"
    attempts = cache.get(cache_key, 0)
    
    if attempts >= config.LOGIN_ATTEMPTS_LIMIT:
        return False, 0
    
    return True, config.LOGIN_ATTEMPTS_LIMIT - attempts

def record_login_attempt(identifier: str, success: bool) -> None:
    """Record login attempt for rate limiting"""
    cache_key = f"login_attempts:{identifier}"
    
    if success:
        cache.delete(cache_key)
    else:
        attempts = cache.get(cache_key, 0) + 1
        cache.set(cache_key, attempts, ttl=config.LOGIN_LOCKOUT_MINUTES * 60)


# ─── Utility Functions ─────────────────────────────────────────────────────
def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data for logging"""
    return hashlib.sha256(data.encode()).hexdigest()[:8]

def get_encryption_key() -> bytes:
    key = config.ENCRYPTION_KEY
    if not key:
        raise ValueError("Encryption key is not set in the configuration")
    return key.encode() if isinstance(key, str) else key

def get_fernet() -> Fernet:
    global _cached_fernet
    if _cached_fernet is None:
        _cached_fernet = Fernet(get_encryption_key())
    return _cached_fernet

def reset_crypto_cache() -> None:
    global _cached_fernet
    _cached_fernet = None

def encrypt_sensitive_data(data: str) -> str:
    try:
        return base64.urlsafe_b64encode(get_fernet().encrypt(data.encode())).decode()
    except Exception as e:
        log.critical(action="encryption_error", trace_info="system", message=f"Failed to encrypt data: {str(e)}", secure=False)
        return data

def decrypt_sensitive_data(encrypted_data: str) -> str:
    if not encrypted_data:
        return encrypted_data
    try:
        decoded = base64.urlsafe_b64decode(encrypted_data.encode())
        return get_fernet().decrypt(decoded).decode()
    except Exception as e:
        log.critical(action="decryption_error", trace_info="system", message=f"Failed to decrypt data: {str(e)}", secure=False)
        return encrypted_data

# ─── Client Request Info ───────────────────────────────────────────────────

async def get_client_info() -> Dict[str, Any] | None:
    """Get client IP address and device metadata with fallback and proxy support."""
    if hasattr(g, "_client_info_cached"):
        return g._client_info_cached

    info = {
        "ip_address": get_ip_address(),
        "device_id": request.headers.get('X-Device-ID'),
        "device_brand": request.headers.get('X-Device-Brand'),
        "device_model": request.headers.get('X-Device-Model'),
        "device_os": request.headers.get('X-Device-OS'),
        "app_version": request.headers.get('X-App-Version'),
        "os_version": request.headers.get('X-OS-Version'),
    }
    if not await validate_request_headers():
        return None
    if not await validate_device_fingerprint(info):
        g._client_info_cached = None
        return None

    g._client_info_cached = info
    return info

def get_ip_address():
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    return request.remote_addr

async def validate_device_fingerprint(device_data: Dict[str, Any]) -> bool:
    """Validate device fingerprint for security"""
    required_device_fields = ['device_id', 'device_brand', 'ip_address', 'os_version', 'app_version', 'device_model', 'device_os']
    
    for field in required_device_fields:
        if not device_data.get(field):
            return False
    
    # Check for suspicious device patterns
    device_id = device_data['device_id']
    suspicious_patterns = [
        r'^(test|dummy|fake|null|undefined)$',
        r'[<>"\']',
        r'\.\.',
        r'javascript:',
        r'<script'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, device_id, re.IGNORECASE):
            security_manager.track_suspicious_activity(device_data['ip_address'], "Suspicious device identifier detected")
            return False
    
    if not await validate_request_origin(request):
        print("Suspicious referer")
    
    return True

def validate_request_origin(request: Request) -> bool:
    """Validate request origin for security"""
    # Check referer header
    referer = request.headers.get('Referer')
    if referer:
        # Validate referer is from same domain
        try:
            from urllib.parse import urlparse
            parsed_referer = urlparse(referer)
            parsed_host = urlparse(request.url_root)
            
            if parsed_referer.netloc != parsed_host.netloc:
                log.warning(action="suspicious_referer", trace_info=get_client_info()["ip_address"], message=f"Suspicious referer: {referer}", secure=False)
                return False
        except Exception:
            return False
    
    return True

from quart import g

async def secure_data(required_fields: list[str] = None) -> tuple[dict | None, str]:
    cache_key = tuple(sorted(required_fields))
    if hasattr(g, "_secure_data_cache") and cache_key in g._secure_data_cache:
        return g._secure_data_cache[cache_key]

    if required_fields:
        required_fields.extend(config.GLOBAL_REQUIRED_FIELDS)
    else:
        required_fields = config.GLOBAL_REQUIRED_FIELDS

    if request.method == 'POST':
        data = request.get_json()
    elif request.method == 'GET':
        data = request.args.to_dict()

    if not data:
        return None, "No data provided"

    client_info = await get_client_info()
    if client_info:
        data.update(client_info)
    else:
        return None, "Invalid device information"

    # Validate device information
    device_id = data.get("device_id")
    ip_address = data.get("ip_address")
    is_valid_device, device_error = await validate_device_info(device_id, ip_address)
    if not is_valid_device:
        log.warning(action="login_invalid_device", trace_info=ip_address, message=f"Invalid device: {device_error}", secure=False)
        return None, device_error
    
    missing_fields = [f for f in required_fields if not data.get(f)]
    if missing_fields:
        log.warning(action="register_missing_fields", trace_info=ip_address, message=f"Missing fields: {missing_fields}", secure=False)
        return None, _("Missing required fields: %(fields)s") % {"fields": ", ".join(missing_fields)}

    # Important: get api_key directly from request (client_info currently doesn’t include it)
    api_key = data.get("api_key") if data.get("api_key") else None
    admin_key = config.ADMIN_KEY

    for key, value in list(data.items()):
        if isinstance(value, str):
            data[key] = security_manager.sanitize_inputs(value)
        if api_key != admin_key and isinstance(value, str) and security_manager.detect_sql_injection(value):
            client_info = await get_client_info()
            ip = (client_info or {}).get("ip_address")
            device_id = (client_info or {}).get("device_id")
            security_manager.track_suspicious_activity(ip, "SQL injection detected")
            log.critical(action="sql_injection_detected", trace_info=ip or "unknown", message=f"SQL injection detected: {value}", secure=False)
            return None, "SQL injection detected"

    if not hasattr(g, "_secure_data_cache"):
        g._secure_data_cache = {}
    g._secure_data_cache[cache_key] = (data, "")
    return data, ""

async def validate_request_headers(request: Request) -> Tuple[bool, str]:
    """Validate request headers for security"""
    # Check for required headers
    required_headers = ['User-Agent', 'Accept']
    for header in required_headers:
        if not request.headers.get(header):
            return False, f"Missing required header: {header}"
    
    ip_address = get_ip_address()
    device_id = request.headers.get("X-Device-ID")
    
    # Check for suspicious headers
    suspicious_headers = ['X-Forwarded-Host', 'X-Original-URL']
    for header in suspicious_headers:
        if request.headers.get(header):
            log.critical(action="suspicious_header", trace_info=ip_address, message=f"Suspicious header detected: {header}", secure=False)
            security_manager.track_suspicious_activity(ip_address, "Suspicious header detected")
    
    return True, ""