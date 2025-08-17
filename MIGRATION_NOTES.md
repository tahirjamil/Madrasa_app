# Quart to FastAPI Migration Notes

## Overview
This document outlines the migration from Quart to FastAPI for the Madrasa Management System. The migration preserves all existing functionality while leveraging FastAPI's modern features like automatic validation, OpenAPI documentation, and better type hints support.

## Migration Status
- ✅ Dependencies updated (requirements.txt)
- ✅ Main application file converted (app.py)
- ✅ Config module updated
- 🚧 API routes conversion in progress
- ⏳ Web routes pending
- ⏳ Admin routes pending
- ⏳ Tests pending
- ⏳ Deployment configuration pending

## Key Changes

### 1. Dependencies
**Removed:**
- Quart
- quart-cors
- quart-csrf
- quart-babel
- hypercorn

**Added:**
- fastapi[all]>=0.109.0
- uvicorn[standard]>=0.25.0
- pydantic>=2.5.0
- pydantic-settings>=2.1.0
- python-multipart>=0.0.6
- opentelemetry-instrumentation-fastapi

### 2. Application Structure

#### Main App (app.py)
- **Before:** `app = MadrasaApp(__name__)` (Quart app)
- **After:** `app = FastAPI(title=..., version=..., lifespan=...)` 

#### Lifecycle Events
- **Before:** `@app.before_serving` and `@app.after_serving`
- **After:** `lifespan` context manager with startup and shutdown events

#### Middleware
- **Before:** Direct middleware assignment and decorators
- **After:** `app.add_middleware()` with custom middleware classes

#### Static Files
- **Before:** `send_from_directory()`
- **After:** `app.mount("/static", StaticFiles(directory="static"))`

### 3. Route Conversion Patterns

#### Blueprint to Router
```python
# Before (Quart)
from quart import Blueprint
api = Blueprint("api", __name__)

# After (FastAPI)
from fastapi import APIRouter
api = APIRouter(prefix="/api/v1")
```

#### Route Decorators
```python
# Before (Quart)
@api.route("/register", methods=["POST"])
async def register():
    data = await request.get_json()
    # manual validation

# After (FastAPI)
@api.post("/register")
async def register(data: RegisterRequest):
    # automatic validation via Pydantic
```

#### Request Data Handling
```python
# Before (Quart)
data = await request.get_json()
phone = data.get("phone")
# manual validation

# After (FastAPI)
class RegisterRequest(BaseModel):
    phone: str
    @validator('phone')
    def validate_phone(cls, v):
        # validation logic
        return v
```

#### Response Handling
```python
# Before (Quart)
from quart import jsonify
return jsonify(response), status

# After (FastAPI)
from fastapi.responses import JSONResponse
return JSONResponse(content=response, status_code=status)
```

### 4. Authentication & Security

#### API Key Validation
```python
# Before (Quart)
@require_api_key  # decorator checking headers

# After (FastAPI)
async def require_api_key(api_key: Optional[str] = Depends(api_key_header)):
    # dependency injection
```

#### Session Management
- Added `SessionMiddleware` for session support
- Session access via `request.session` instead of `quart.session`

### 5. Helper Functions Migration

Created `utils/helpers/fastapi_helpers.py` with FastAPI-specific patterns:

1. **secure_data** → Pydantic models with validators
2. **rate_limit** → Decorator compatible with FastAPI
3. **handle_async_errors** → Exception handling decorator
4. **require_api_key** → FastAPI dependency
5. **get_client_info** → Dependency extracting client data from headers

### 6. Template Rendering
```python
# Before (Quart)
from quart import render_template
return await render_template('404.html'), 404

# After (FastAPI)
from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="templates")
return templates.TemplateResponse('404.html', {'request': request}, status_code=404)
```

### 7. WebSocket Handling (TODO)
- Need to convert Quart WebSocket handlers to FastAPI WebSocket endpoints

### 8. Background Tasks (TODO)
- Replace Quart background tasks with FastAPI BackgroundTasks

## Manual Follow-ups Required

### 1. Translation System
- Quart-Babel is removed
- Need to implement a custom translation solution or use a FastAPI-compatible i18n library
- Currently, all `_()` gettext calls have been replaced with plain strings

### 2. CSRF Protection
- quart-csrf is removed
- Need to implement custom CSRF protection for form submissions
- Consider using a library like `fastapi-csrf-protect`

### 3. Global Request Context
- No `g` object in FastAPI
- Use `request.state` for request-scoped data
- Use dependencies for shared data injection

### 4. Testing
- Update all tests to use `httpx.AsyncClient` or `TestClient` from FastAPI
- Update test fixtures for FastAPI app

### 5. Rate Limiting
- Current implementation uses in-memory storage
- Consider using Redis for production rate limiting

### 6. Error Handlers
- Convert all error handlers to FastAPI exception handlers
- Ensure error responses maintain the same format

## Deployment Changes

### 1. Server Command
```bash
# Before
hypercorn app:app --bind 0.0.0.0:8000

# After  
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

### 2. Docker Updates
- Update Dockerfile to use uvicorn
- Remove hypercorn configuration files
- Update docker-compose.yml

### 3. Environment Variables
- No changes to environment variables
- Configuration system remains the same

## Benefits of Migration

1. **Better Performance**: FastAPI is generally faster than Quart
2. **Automatic Documentation**: OpenAPI/Swagger docs at `/docs` and `/redoc`
3. **Type Safety**: Better IDE support with Pydantic models
4. **Validation**: Automatic request/response validation
5. **Modern Python**: Better async/await patterns
6. **Dependency Injection**: Cleaner code organization
7. **Active Community**: Larger ecosystem and better support

## Risks and Considerations

1. **Breaking Changes**: Some middleware and decorators work differently
2. **Session Handling**: Different session management approach
3. **WebSocket API**: Different WebSocket implementation
4. **Template Context**: No automatic context processors
5. **Translation System**: Need to replace Babel functionality

## Testing Checklist

- [ ] All API endpoints return correct responses
- [ ] Authentication and authorization work correctly  
- [ ] Rate limiting functions properly
- [ ] File uploads work
- [ ] WebSocket connections (if any) work
- [ ] Background tasks execute correctly
- [ ] Templates render with correct context
- [ ] Static files are served
- [ ] Error handling maintains same behavior
- [ ] Database connections pool correctly
- [ ] Redis/KeyDB connections work
- [ ] OpenTelemetry tracing works
- [ ] All tests pass

## Next Steps

1. Complete API route conversion
2. Convert web routes (HTML responses)
3. Convert admin routes
4. Update all tests
5. Implement translation system
6. Update deployment configuration
7. Comprehensive testing
8. Performance benchmarking
9. Update documentation