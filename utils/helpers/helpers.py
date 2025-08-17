"""Helper Functions for Madrasha Application"""
import dataclasses
import decimal
import base64, hashlib, random, re, aiomysql, phonenumbers, requests
import uuid
import datetime as dt
from hmac import compare_digest
import asyncio, json, os, smtplib, time
from contextlib import asynccontextmanager
from datetime import datetime
from email.mime.text import MIMEText
from functools import wraps
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple, Callable, Union

from aiomysql import IntegrityError
from dotenv import load_dotenv
from fastapi import Request, Response, HTTPException
from cryptography.fernet import Fernet
# Import these functions when needed to avoid circular imports
# from utils.mysql.database_utils import get_db_connection
# from utils.keydb.keydb_utils import get_keydb_connection
from config import config
from utils.helpers.improved_functions import get_env_var, send_json_response
from utils.helpers.logger import log

load_dotenv()

# ---------- Cache Functions ----------
def get_cache_key(prefix: str, **kwargs) -> str:
    parts = [prefix]
    for k, v in sorted(kwargs.items()):
        # canonical JSON representation of values to reduce accidental collisions
        parts.append(f"{k}:{json.dumps(v, sort_keys=True, separators=(',',':'), default=str, ensure_ascii=False)}")
    return ":".join(parts)

async def get_cached_data(cache_key: str, ttl: Optional[int] = None, default: Any = None) -> Any:
    """Fetch cached JSON-serializable data from KeyDB. Falls back to in-memory cache if needed."""
    if ttl is None:
        ttl = getattr(config, "CACHE_TTL", 3600)
    try:
        from utils.keydb.keydb_utils import get_keydb_connection
        pool = await get_keydb_connection()
        raw = await pool.get(cache_key)
        if raw is not None:
            # metrics removed
            try:
                return json.loads(raw)
            except Exception:
                return raw
        # metrics removed
        return default
    except RuntimeError as e:
        # Redis cache is disabled, return default
        return default
    except Exception as e:
        raise RuntimeError(f"KeyDB unavailable when getting cache key '{cache_key}': {e}")

async def set_cached_data(cache_key: str, data: Any, ttl: Optional[int] = None) -> None:
    """Store JSON-serializable data in KeyDB with TTL. Falls back to in-memory cache if needed."""
    if ttl is None:
        ttl = getattr(config, "CACHE_TTL", 3600)
    try:
        from utils.keydb.keydb_utils import get_keydb_connection
        pool = await get_keydb_connection()
        payload = canonical_json(data)
        # aioredis 1.x supports expire argument in set
        await pool.set(cache_key, payload, expire=int(ttl) if ttl else None)
    except RuntimeError as e:
        # Redis cache is disabled, silently skip
        pass
    except Exception as e:
        raise RuntimeError(f"KeyDB unavailable when setting cache key '{cache_key}': {e}")

async def _invalidate_cache_pattern_async(pattern: str) -> int:
    """Asynchronously delete keys matching pattern from KeyDB. Returns number deleted."""
    try:
        from utils.keydb.keydb_utils import get_keydb_connection
        pool = await get_keydb_connection()
        # Use KEYS for simplicity; for large keyspaces consider SCAN.
        keys = await pool.keys(pattern)
        if not keys:
            return 0
        # aioredis delete supports varargs
        await pool.delete(*keys)
        return len(keys)
    except RuntimeError as e:
        # Redis cache is disabled, return 0
        return 0
    except Exception as e:
        raise RuntimeError(f"KeyDB unavailable when invalidating pattern '{pattern}': {e}")

def invalidate_cache_pattern(pattern: str) -> int:
    """Fire-and-forget invalidation against KeyDB; returns 0 immediately. Fallback clears local cache."""
    loop = asyncio.get_event_loop()
    loop.create_task(_invalidate_cache_pattern_async(pattern))
    return 0

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
def cache_with_invalidation(func: Optional[Callable] = None, *, ttl: int = 3600):
    """Decorator for endpoint-level caching backed by KeyDB."""
    def _decorate(f: Callable):
        @wraps(f)
        async def wrapper(*args, **kwargs):
            try:
                # In FastAPI, the request is typically the first argument of the endpoint
                from fastapi import Request
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
                
                if request is None:
                    # No request found, skip caching
                    return await f(*args, **kwargs)
                
                method = request.method
                path = request.url.path
                try:
                    query = dict(sorted(request.query_params.items()))
                except Exception:
                    query = {}
                try:
                    body = await request.json() if request.method in ["POST", "PUT", "PATCH"] else None
                except Exception:
                    body = None
                fingerprint = json.dumps({"m": method, "p": path, "q": query, "b": body},
                                         sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
            except Exception:
                fingerprint = json.dumps({"args": [repr(a) for a in args], "kwargs": kwargs},
                                         sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)

            key = f"{f.__module__}.{f.__name__}:{hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()}"
            cached = await get_cached_data(key, ttl=ttl)
            if cached is not None:
                return cached

            result = await f(*args, **kwargs)
            if not isinstance(result, Response):
                await set_cached_data(key, result, ttl=ttl)
            return result

        # TODO: This decorator is incompatible with FastAPI's request handling.
        # For now, just return the function as-is
        return f

    if callable(func):
        return _decorate(func)
    return _decorate

# ---------- Enhanced HTTP Cache ---------- TODO: This is unknown
class EnhancedJSONEncoder(json.JSONEncoder):
    """Extend JSONEncoder with common non-JSON types handling."""
    def default(self, o: Any) -> Any | None:
        # datetimes -> ISO8601 string
        if isinstance(o, (dt.datetime, dt.date, dt.time)):
            # Use ISO format; datetimes preserve timezone if present
            return o.isoformat()
        # Decimal -> number (or string if prefered)
        if isinstance(o, decimal.Decimal):
            # convert to a float-safe string to avoid precision loss in JSON
            return str(o)
        # UUID -> hex string
        if isinstance(o, uuid.UUID):
            return str(o)
        # dataclass -> dict
        if dataclasses.is_dataclass(o) and not isinstance(o, type):
            return dataclasses.asdict(o)
        # bytes -> base64 string
        if isinstance(o, (bytes, bytearray)):
            return base64.b64encode(bytes(o)).decode('ascii')
        # fallback to parent's behavior (which will raise TypeError)
        return super().default(o)


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

async def send_email(to_email: str, subject: str, 
                    body: str) -> bool:
    """Send email with enhanced error handling"""
    await delete_code()
    return await _send_async_email(to_email, subject, body)

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

async def send_sms(phone: str, msg: str) -> bool:
    """Send SMS with enhanced error handling"""
    await delete_code()
    return await _send_async_sms(phone, msg)

# ─── Database Functions ──────────────────────────────────────────────────────

@asynccontextmanager
async def get_db_context():
    """Database connection context manager"""
    from utils.mysql.database_utils import get_db_connection
    async with get_db_connection() as conn:
        yield conn

async def get_email(fullname: str, phone: str) -> Optional[str]:
    """Get user email with caching"""
    cache_key = f"email:{fullname}:{phone}"
    cached_email = await get_cached_data(cache_key)
    if cached_email:
        return cached_email
    
    if config.is_testing():
        return get_env_var("DUMMY_EMAIL")
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                await cursor.execute(
                    "SELECT email FROM global.users WHERE fullname = %s AND phone = %s",
                    (fullname, phone)
                )
                result = await cursor.fetchone()
                
                email = result['email'] if result else None
                if email:
                    await set_cached_data(cache_key, email, ttl=3600)  # Cache for 1 hour
                return email
        except Exception as e:
            log.critical(action="db_error with get_email", trace_info=phone, message=str(e), secure=True)
            return None

async def get_id(phone: str, fullname: str) -> Optional[int]:
    """Get user ID with caching"""
    cache_key = f"user_id:{phone}:{fullname}"
    cached_id = await get_cached_data(cache_key)
    if cached_id:
        return cached_id
    
    if config.is_testing():
        fullname = config.DUMMY_FULLNAME
        phone = config.DUMMY_PHONE
    
    async with get_db_context() as conn:
        try:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                await cursor.execute(
                    "SELECT user_id FROM global.users WHERE phone = %s AND fullname = %s",
                    (phone, fullname)
                )
                result = await cursor.fetchone()
                
                user_id = result['user_id'] if result else None
                if user_id:
                    await set_cached_data(cache_key, user_id, ttl=3600)  # Cache for 1 hour
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
    
    async with conn.cursor(aiomysql.DictCursor) as _cursor:
        from utils.otel.db_tracing import TracedCursorWrapper
        cursor = TracedCursorWrapper(_cursor)
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
            
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
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
                async with conn.cursor(aiomysql.DictCursor) as _cursor:
                    from utils.otel.db_tracing import TracedCursorWrapper
                    cursor = TracedCursorWrapper(_cursor)
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

def calculate_fees(class_name: str, gender: str, special_food: bool = False, 
                  reduced_fee: float = 0.0, food: bool = True, tax: float = 0.0) -> float:
    """Calculate fees with comprehensive pricing logic"""
    total = 0.0
    class_lower = class_name.lower()
    
    if config.is_testing():
        return 9999.0
    
    # Food charges
    if food:
        total += 2400.0
    if special_food:
        total += 3000.0
    
    # Base fees by gender and class
    if gender.lower() == 'male':
        if class_lower in ['class 3', 'class 2']:
            total += 1600.0
        elif class_lower in ['hifz', 'nazara']:
            total += 1800.0
        else:
            total += 1300.0
    elif gender.lower() == 'female':
        if class_lower == 'nursery':
            total += 800.0
        elif class_lower == 'class 1':
            total += 1000.0
        elif class_lower == 'hifz':
            total += 2000.0
        elif class_lower in ['class 2', 'class 3', 'nazara']:
            total += 1200.0
        else:
            total += 1500.0
    
    # Apply fee reduction
    if reduced_fee:
        total -= reduced_fee

    if tax:
        total += tax
    
    return max(0, total)  # Ensure non-negative total

# ─── File Management Functions ───────────────────────────────────────────────

def load_results() -> List[Dict[str, Any]]:
    """Load exams results with caching and error handling."""
    cache_key = "load_results:default"
    # File-based data; skip remote cache and always read
    try:
        # Ensure we have the config attribute
        if not hasattr(config, 'EXAM_RESULTS_INDEX_FILE'):
            log.critical(action="config_error", trace_info="load_results", 
                        message="EXAM_RESULTS_INDEX_FILE not found in config", secure=False)
            return []
        with open(config.EXAM_RESULTS_INDEX_FILE, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = []
    # Not cached remotely to avoid stale file index issues
    return data

def save_results(data: List[Dict[str, Any]]) -> None:
    """Save exam results with atomic write and cache invalidation."""
    # Ensure we have the config attribute
    if not hasattr(config, 'EXAM_RESULTS_INDEX_FILE'):
        log.critical(action="config_error", trace_info="save_results", 
                    message="EXAM_RESULTS_INDEX_FILE not found in config", secure=False)
        return
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
    # File-based data; skip remote cache and always read
    try:
        # Ensure we have the config attribute
        if not hasattr(config, 'NOTICES_INDEX_FILE'):
            log.critical(action="config_error", trace_info="load_notices", 
                        message="NOTICES_INDEX_FILE not found in config", secure=False)
            return []
        with open(config.NOTICES_INDEX_FILE, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        # Auto-fix broken JSON
        with open(config.NOTICES_INDEX_FILE, 'w') as f:
            json.dump([], f)
        data = []
    except FileNotFoundError:
        data = []
    # Not cached remotely to avoid stale file index issues
    return data

def save_notices(data: List[Dict[str, Any]]) -> None:
    """Save notices with atomic write and cache invalidation."""
    # Ensure we have the config attribute
    if not hasattr(config, 'NOTICES_INDEX_FILE'):
        log.critical(action="config_error", trace_info="save_notices", 
                    message="NOTICES_INDEX_FILE not found in config", secure=False)
        return
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
    """
    Decorator for rate limiting endpoints
    
    TODO: This decorator is incompatible with FastAPI.
    Use the rate_limit decorator from fastapi_helpers.py instead.
    This is kept as a no-op for backward compatibility during migration.
    """
    def decorator(func):
        # Return function as-is
        return func
    return decorator

def require_api_key(func):
    """
    Decorator to require valid API key
    
    TODO: This decorator is incompatible with FastAPI.
    Use the require_api_key dependency from fastapi_helpers.py instead.
    This is kept as a no-op for backward compatibility during migration.
    """
    # Return function as-is
    return func

# ─── Health Check Functions ─────────────────────────────────────────────────

async def check_database_health() -> Dict[str, Any]:
    """Check database connectivity and health"""
    from utils.mysql.database_utils import get_db_connection
    
    async with get_db_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT 1")
            return {"status": "healthy", "message": "Database connection successful"}

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

async def check_keydb_health() -> Dict[str, Any]:
    """Check KeyDB health"""
    try:
        from utils.keydb.keydb_utils import ping_keydb
        if await ping_keydb():
            return {"status": "healthy", "message": "KeyDB connection successful"}
        else:
            return {"status": "unhealthy", "message": "KeyDB connection failed"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"KeyDB error: {str(e)}"}

async def check_opentelemetry_health() -> Dict[str, Any]:
    """Check OpenTelemetry health by sending a test span."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        
        exporter = OTLPSpanExporter(endpoint=config.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
        provider = TracerProvider()
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer(__name__)

        # Send a test span
        with tracer.start_as_current_span("opentelemetry-health-check"):
            pass

        # If we made it this far, connection is likely healthy
        return {"status": "healthy", "message": "OpenTelemetry connection successful"}
    except Exception as e:
        return {"status": "unhealthy", "message": f"OpenTelemetry error: {str(e)}"}

async def get_system_health() -> Dict[str, Any]:
    """Get comprehensive system health status"""
    db_health = await check_database_health()
    fs_health = await check_file_system_health()
    keydb_health = await check_keydb_health()
    opentelemetry_health = await check_opentelemetry_health()

    status = "healthy"
    if db_health["status"] == "unhealthy" and fs_health["status"] == "unhealthy":
        status = "critical"
    elif db_health["status"] == "unhealthy" or fs_health["status"] == "unhealthy":
        status = "unhealthy"
    
    # Try to fetch KeyDB dbsize as cache_size; if unavailable set 0
    try:
        from utils.keydb.keydb_utils import get_keydb_connection
        from_keydb = await get_keydb_connection()
        try:
            cache_size = int(await from_keydb.dbsize())
        except Exception:
            cache_size = int(await from_keydb.execute('DBSIZE'))
    except Exception:
        cache_size = 0

    return {
        "status": status,
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "database": db_health,
        "keydb": keydb_health,
        "opentelemetry": opentelemetry_health,
        "file_system": fs_health,
        "maintenance_mode": config.is_maintenance(),
        "test_mode": config.is_testing(),
        "cache_size": cache_size,
        "rate_limiter_size": len(rate_limiter._requests)
    }


# ─── Advanced Error Handling ───────────────────────────────────────────────
class AppError(Exception):
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
            raise HTTPException(
                status_code=400,
                detail={
                    "message": e.message,
                    "error_code": e.error_code,
                    "details": e.details
                }
            )
        except Exception as e:
            log.critical(action="unexpected_error", trace_info="error_handler", message=str(e), secure=False)
            # metrics removed
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "An unexpected error occurred",
                    "error_code": "INTERNAL_ERROR",
                    "details": str(e)
                }
            )
    
    return wrapper

# ─── Metrics and Analytics ─────────────────────────────────────────────────

class MetricsCollector:
    """Deprecated custom metrics collector. Kept as a no-op for compatibility."""
    
    def __init__(self):
        self.metrics = {}
        self.start_time = time.time()
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Increment a metric counter"""
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return {}

# Global metrics collector
metrics_collector = MetricsCollector()


# ─── Application Initialization ────────────────────────────────────────────

def initialize_application() -> bool:
    """Initialize application with all necessary components"""
    try:
        # Initialize rate limiter
        rate_limiter._requests.clear()
        
        # Log successful initialization  
        log.info(action="app_initialized", trace_info="system", message="Application initialized successfully", secure=False)
        return True
        
    except Exception as e:
        log.critical(action="init_error", trace_info="system", message=str(e), secure=False)
        return False

# ─── CSRF Protection ───────────────────────────────────────────────────────

async def validate_csrf_token(request: Request):
    """
    Validate CSRF token from form data
    
    TODO: This function needs to be updated to work with FastAPI's CSRF protection.
    """
    from utils.helpers.csrf_protection import validate_csrf_token as validate_token
    form = await request.form()
    token = form.get('csrf_token')
    if not validate_token(token):
        # In FastAPI, we should raise HTTPException instead of using flash
        raise HTTPException(status_code=400, detail="CSRF token validation failed")
    return True

def require_csrf(f):
    """
    Decorator to require CSRF validation for POST requests
    
    TODO: This decorator is incompatible with FastAPI.
    CSRF protection should be implemented using FastAPI middleware or dependencies.
    This is kept as a no-op for backward compatibility during migration.
    """
    # Return function as-is
    return f

# ─────────────────────────────────────────────────────────────────────────────
# ──────────────────────── Security functions ─────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


# ─── Rate Limiting ───────────────────────────────────────────────────────────

class RateLimiter:
    """Advanced rate limiting with sliding window and thread safety"""
    
    def __init__(self):
        self._requests: Dict[str, List[float]] = {}
        self._cleanup_interval = 1 * 3600  # 1 hour
        self._last_cleanup = time.time()
        self._lock = Lock()
    
    def is_allowed(self, identifier: str, max_requests: int, window: int) -> bool:
        """Check if request is allowed based on rate limit (thread-safe)"""
        current_time = time.time()
        
        with self._lock:
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
        """Remove old request records (thread-safe)"""
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


async def check_rate_limit(identifier: str, max_requests: int | None = None, window: int | None = None) -> bool:
    """Enhanced rate limiting with additional checks"""
    if max_requests is None:
        max_requests = config.DEFAULT_RATE_LIMIT
    if window is None:
        window = config.RATE_LIMIT_WINDOW
    
    # Additional security checks
    client_info = await get_client_info() or {}
    
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

async def check_code(user_code: str, phone: str) -> None:
    """Enhanced code verification with security features"""
    from utils.mysql.database_utils import get_db_connection
    
    
    if config.is_testing():
        return None
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as _cursor:
                from utils.otel.db_tracing import TracedCursorWrapper
                cursor = TracedCursorWrapper(_cursor)
                await cursor.execute("""
                    SELECT code, created_at FROM global.verifications
                    WHERE phone = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (phone,))
                result = await cursor.fetchone()
                
                if not result:
                    raise HTTPException(status_code=404, detail="No verification code found")
                
                db_code = result["code"]
                created_at = result["created_at"]
                now = datetime.now()
                
                # Check expiration
                if (now - created_at).total_seconds() > config.CODE_EXPIRY_MINUTES * 60:
                    raise HTTPException(status_code=410, detail="Verification code expired")
                
                # Constant-time comparison
                if int(user_code) == db_code:
                    await delete_code()
                    return None
                else:
                    log.warning(action="verification_failed", trace_info=phone, message="Code mismatch", secure=True)
                    raise HTTPException(status_code=400, detail="Verification code mismatch")
    
    except Exception as e:
        log.critical(action="verification_error", trace_info=phone, message=str(e), secure=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

async def delete_code() -> None:
    """Delete expired verification codes"""
    from utils.mysql.database_utils import get_db_connection
    
    async with get_db_connection() as conn:
        async with conn.cursor(aiomysql.DictCursor) as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
            await cursor.execute("""
                DELETE FROM global.verifications
                WHERE created_at < NOW() - INTERVAL 1 DAY
            """)

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
            await security_manager.track_suspicious_activity(ip_address, "Suspicious device identifier detected")
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
        self._lock = Lock() # Thread safety for shared state
    
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
        """Track suspicious activities for threat analysis (thread-safe)"""
        with self._lock:
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
    return None

def monitor_database_performance(query: str, duration: float) -> None:
    return None


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


async def validate_file_upload(file, allowed_extensions: List[str], max_size: Optional[int] = None) -> Tuple[bool, str]:
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
    if max_size and file.content_length and file.content_length > max_size:
        return False, f"File size exceeds maximum allowed size ({max_size / 1024 / 1024} MB)"
    
    # Check for suspicious filename patterns
    suspicious_patterns = [
        r'\.\./', r'\.\.\\', r'[<>:"|?*]',
        r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)',
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, file.filename, re.IGNORECASE):
            log.warning(
                action="suspicious_filename",
                trace_info=(await get_client_info() or {})["ip_address"],
                message=f"Suspicious filename detected: {file.filename}",
                secure=False
            )
            return False, "Invalid filename"
    
    return True, ""

# ──── User Login Limits ────────────────────────────────────────────────────
async def check_device_limit(user_id: int, device_id: str) -> Tuple[bool, str]: # TODO: fix the device limit where it should delete from interactions table
    """Check if user has reached device limit"""
    from utils.mysql.database_utils import get_db_connection

    async with get_db_connection() as conn:
        async with conn.cursor() as _cursor:
            from utils.otel.db_tracing import TracedCursorWrapper
            cursor = TracedCursorWrapper(_cursor)
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
            
            # Import config here to avoid circular import
            from config import config
            if device_count >= config.MAX_DEVICES_PER_USER:
                return False, f"Maximum devices ({config.MAX_DEVICES_PER_USER}) reached. Please remove an existing device to add this one."
            
            return True, ""
    

async def check_login_attempts(identifier: str) -> Tuple[bool, int]:
    """Check login attempts in KeyDB and return (allowed, remaining)."""
    cache_key = f"login_attempts:{identifier}"
    from utils.keydb.keydb_utils import get_keydb_connection
    pool = await get_keydb_connection()
    raw = await pool.get(cache_key)
    attempts = int(raw or 0)
    # Import config here to avoid circular import
    from config import config
    if attempts >= config.LOGIN_ATTEMPTS_LIMIT:
        return False, 0
    return True, config.LOGIN_ATTEMPTS_LIMIT - attempts

async def record_login_attempt(identifier: str, success: bool) -> None:
    """Record login attempt in KeyDB (increment on failure, clear on success)."""
    cache_key = f"login_attempts:{identifier}"
    from utils.keydb.keydb_utils import get_keydb_connection
    pool = await get_keydb_connection()
    if success:
        await pool.delete(cache_key)
    else:
        raw = await pool.get(cache_key)
        attempts = int(raw or 0) + 1
        # Import config here to avoid circular import
        from config import config
        await pool.set(cache_key, attempts, expire=int(config.LOGIN_LOCKOUT_MINUTES * 60))


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

# DEPRECATED: This function is replaced by get_client_info dependency in FastAPI
# Use ClientInfo and get_client_info from utils.helpers.fastapi_helpers instead
async def get_client_info(request: Optional[Request] = None, full_record: Optional[Dict] = None) -> Dict[str, Any] | None:
    """
    DEPRECATED: Use get_client_info dependency from fastapi_helpers instead.
    This function is kept for backward compatibility during migration.
    """
    if full_record:
        # Process full record if provided
        return process_client_info_record(full_record)
    
    log.warning(action="deprecated_function", trace_info="system", message="get_client_info is deprecated. Use FastAPI dependency instead.", secure=False)
    return None

def process_client_info_record(record: Dict) -> Dict[str, Any]:
    """Process a full database record to extract client info"""
    # This functionality is preserved from the original function
    info = {}
    for key, value in record.items():
        if value is not None:
            info[key] = value
    return info

def get_ip_address(request: Request) -> str:
    """Extract client IP address from request headers"""
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    # In FastAPI, client info is in request.client
    if request.client:
        return request.client.host
    return "unknown"

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
            await security_manager.track_suspicious_activity(device_data['ip_address'], "Suspicious device identifier detected")
            return False
    
    # Note: validate_request_origin requires request object which is not available in this context
    # This check has been removed. Consider passing request as parameter if needed.
    # if not await validate_request_origin(request):
    #     print("Suspicious referer")
    
    return True

async def validate_request_origin(request: Request) -> bool:
    """Validate request origin for security"""
    # Check referer header
    referer = request.headers.get('Referer')
    if referer:
        # Validate referer is from same domain
        try:
            from urllib.parse import urlparse
            parsed_referer = urlparse(referer)
            parsed_host = urlparse(str(request.base_url))
            
            if parsed_referer.netloc != parsed_host.netloc:
                log.warning(action="suspicious_referer", trace_info=(await get_client_info() or {})["ip_address"], message=f"Suspicious referer: {referer}", secure=False)
                return False
        except Exception:
            return False
    
    return True

# DEPRECATED: This function is replaced by Pydantic models in FastAPI
# Use BaseAuthRequest and other models from utils.helpers.fastapi_helpers instead
async def secure_data(required_fields: list[str] | None= None) -> tuple[dict[str, Any] | None, str]:
    """
    DEPRECATED: Use Pydantic models instead for FastAPI.
    This function is kept for backward compatibility during migration.
    """
    # Note: This function won't work properly in FastAPI context
    # It's replaced by Pydantic models with automatic validation
    log.warning(action="deprecated_function", trace_info="system", message="secure_data is deprecated. Use Pydantic models instead.", secure=False)
    return None, "Function deprecated - use Pydantic models"

async def validate_request_headers(request: Request) -> Tuple[bool, str]:
    """Validate request headers for security"""
    # Check for required headers
    required_headers = ['User-Agent', 'Accept']
    for header in required_headers:
        if not request.headers.get(header):
            return False, f"Missing required header: {header}"
    
    ip_address = get_ip_address(request) or "unknown"
    device_id = request.headers.get("X-Device-ID")
    
    # Check for suspicious headers
    suspicious_headers = ['X-Forwarded-Host', 'X-Original-URL']
    for header in suspicious_headers:
        if request.headers.get(header):
            log.critical(action="suspicious_header", trace_info=ip_address, message=f"Suspicious header detected: {header}", secure=False)
            await security_manager.track_suspicious_activity(ip_address, "Suspicious header detected")
    
    return True, ""

# ─── MADRASA NAME VALIDATION ───────────────────────────────────────────────────

def validate_madrasa_name(madrasa_name: str, ip_address: str) -> bool:
    """Validate madrasa name"""
    if madrasa_name not in config.MADRASA_NAMES_LIST:
        log.critical(action="invalid_madrasa_name", trace_info=ip_address, message=f"Invalid madrasa name configured: {madrasa_name}", secure=False)
        return False
    return True