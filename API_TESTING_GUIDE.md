# API Testing Guide for FastAPI `/docs`

## Overview

Your API routes require specific headers and authentication. This guide explains how to test them using FastAPI's automatic documentation interface.

## Required Authentication & Headers

### 1. API Key Authentication
All API routes require an `X-API-Key` header with one of these values:
- `madrasasecretappkey` (Mobile client)
- `madrasasecretwebkey` (Web client)  
- `madrasasecretadminkey` (Admin client)

### 2. Required Headers
- `X-Device-ID`: Unique device identifier
- `User-Agent`: Browser/device user agent
- `Accept`: Content type acceptance

### 3. Optional Device Headers
- `X-Device-Model`: Device model
- `X-Device-Brand`: Device brand
- `X-Device-OS`: Operating system

## How to Test Using FastAPI `/docs`

### Step 1: Access the Documentation
1. Start your application: `python run_server.py`
2. Open browser: `http://localhost/docs`
3. You'll see the Swagger UI interface

### Step 2: Set Up Authentication
1. Click the **"Authorize"** button (🔒 icon) at the top right
2. In the `X-API-Key` field, enter one of your API keys
3. Click **"Authorize"**

### Step 3: Test Individual Endpoints
**Note**: FastAPI docs doesn't automatically include custom headers, so you'll need to add them manually for each request.

#### Example: Testing `/api/v1/register`

1. Find the `/api/v1/register` endpoint in the docs
2. Click **"Try it out"**
3. In the request body, enter:
```json
{
  "fullname": "Test User",
  "phone": "+880100000001", 
  "password": "testpassword123",
  "madrasa_name": "annur"
}
```
4. **Important**: You'll need to manually add these headers in your browser's developer tools or use a tool like Postman:
   ```
   X-Device-ID: test-device-123
   User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
   Accept: application/json
   ```
5. Click **"Execute"**

## Alternative: Use the Test Script

For easier testing with all required headers automatically included, use the provided test script:

```bash
# Install aiohttp if not already installed
pip install aiohttp

# Run the test script
python test_api_routes.py
```

## Available API Endpoints

### Authentication Endpoints
- `POST /api/v1/register` - User registration
- `POST /api/v1/login` - User login
- `POST /api/v1/account/check` - Check account status
- `POST /api/v1/account/reactivate` - Reactivate account

### Core Endpoints
- `POST /api/v1/members` - Get member information
- `POST /api/v1/add_people` - Add new person

### Payment Endpoints
- `POST /api/v1/calculate_fees` - Calculate fees
- `POST /api/v1/process_payment` - Process payment

### Health Check
- `GET /health` - System health (no authentication required)

## Common Issues & Solutions

### 1. "Invalid API key" Error
- Make sure you're using one of the correct API keys from your `.env` file
- Check that the `X-API-Key` header is properly set

### 2. "Invalid headers" Error
- Ensure `User-Agent` and `Accept` headers are present
- Add a valid `X-Device-ID`

### 3. "Invalid device fingerprint" Error
- This is expected for test requests
- The system validates device information for security

### 4. Rate Limiting
- Some endpoints have rate limits (e.g., 10 requests per minute)
- Wait a few minutes if you hit rate limits

## Testing with Postman/curl

For more advanced testing, you can use Postman or curl with all required headers:

```bash
curl -X POST "http://localhost/api/v1/register" \
  -H "X-API-Key: madrasasecretappkey" \
  -H "X-Device-ID: test-device-123" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d '{
    "fullname": "Test User",
    "phone": "+880100000001",
    "password": "testpassword123", 
    "madrasa_name": "annur"
  }'
```

## Tips for Effective Testing

1. **Start with the health endpoint** - No authentication required
2. **Use consistent device IDs** - Helps with caching and rate limiting
3. **Test with different API keys** - Verify different client types work
4. **Check response status codes** - Understand what each means
5. **Monitor the application logs** - See detailed error information

## Security Notes

- The test script uses test data - don't use real user information
- Device fingerprinting is disabled for testing
- Rate limiting may be more lenient in development mode
- Always use HTTPS in production
