# API Testing Checklist

## Overview
This checklist ensures comprehensive testing of all API endpoints in the Madrasa application.

## Pre-Test Setup
- [ ] Install test dependencies: `pip install aiohttp requests`
- [ ] Set up test environment variables or use `start_test_server.sh`
- [ ] Ensure database is accessible (or use test mode)
- [ ] Clear any test data from previous runs

## Authentication Endpoints

### POST /register
- [ ] Valid registration with all required fields
- [ ] Registration with existing phone number (409 expected)
- [ ] Missing required fields (400 expected)
- [ ] Invalid phone format (400 expected)
- [ ] Weak password (400 expected)
- [ ] Invalid email format (400 expected)
- [ ] SQL injection in fields (400 expected)
- [ ] XSS attempts in name field (400 expected)

### POST /login
- [ ] Valid login with correct credentials
- [ ] Invalid phone number (401 expected)
- [ ] Incorrect password (401 expected)
- [ ] Missing device_id (400 expected)
- [ ] SQL injection attempts (401 expected)
- [ ] Rate limiting after multiple failed attempts

### POST /send_code
- [ ] Valid phone number
- [ ] Invalid phone format (400 expected)
- [ ] Non-existent phone (404 expected)
- [ ] Rate limiting check (429 after limit)

### POST /reset_password
- [ ] Valid reset with correct code
- [ ] Invalid code (401 expected)
- [ ] Expired code (401 expected)
- [ ] Weak new password (400 expected)
- [ ] Missing fields (400 expected)

### POST /account/check
- [ ] Valid phone number check
- [ ] Invalid phone format (400 expected)
- [ ] Check response structure

## Data Endpoints

### POST /members
- [ ] Request without updatedSince
- [ ] Request with valid updatedSince timestamp
- [ ] Invalid timestamp format (400 expected)
- [ ] Check response pagination
- [ ] Verify data structure

### POST /routines
- [ ] Request without filters
- [ ] Request with class filter
- [ ] Request with updatedSince
- [ ] Verify routine structure

### POST /events
- [ ] Request all events
- [ ] Request with date range
- [ ] Check event data structure
- [ ] Verify sorting order

### POST /exams
- [ ] Request all exams
- [ ] Request with filters
- [ ] Check exam schedule format
- [ ] Verify time zone handling

## Payment Endpoints

### POST /due_payments
- [ ] Valid user lookup
- [ ] Non-existent user (404 expected)
- [ ] Invalid phone format (400 expected)
- [ ] Check fee calculation

### POST /get_transactions
- [ ] Valid user transactions
- [ ] Empty transaction history
- [ ] Date range filtering
- [ ] Pagination support

### POST /pay_sslcommerz
- [ ] Valid payment initiation
- [ ] Invalid amount (400 expected)
- [ ] Missing user info (400 expected)
- [ ] Check redirect URL

## File Endpoints

### GET /uploads/profile_img/{filename}
- [ ] Valid image request
- [ ] Non-existent file (404 expected)
- [ ] Directory traversal attempt (400 expected)
- [ ] Check content-type headers

### GET /uploads/notices/{filename}
- [ ] Valid PDF request
- [ ] Invalid file type (404 expected)
- [ ] Check download headers

### GET /uploads/gallery/{gender}/{folder}/{filename}
- [ ] Valid gallery image
- [ ] Invalid gender parameter (400 expected)
- [ ] Invalid folder (404 expected)

## Security Tests

### SQL Injection
- [ ] Login with SQL injection
- [ ] Registration with SQL injection
- [ ] Search with SQL injection
- [ ] All should return 400/401

### XSS Protection
- [ ] Script tags in name fields
- [ ] JavaScript in URLs
- [ ] Event handlers in input
- [ ] All should be sanitized/rejected

### CSRF Protection
- [ ] Admin routes require CSRF token
- [ ] Invalid token rejected
- [ ] Missing token rejected

### Rate Limiting
- [ ] Auth endpoints (10/minute)
- [ ] Data endpoints (100/minute)
- [ ] Verify 429 response
- [ ] Check retry-after header

### Authentication & Authorization
- [ ] Protected routes require auth
- [ ] Invalid tokens rejected
- [ ] Expired tokens handled
- [ ] Admin routes require admin role

## Performance Tests

### Response Times
- [ ] Auth endpoints < 200ms
- [ ] Data endpoints < 500ms
- [ ] File endpoints < 100ms
- [ ] Check under load

### Concurrent Requests
- [ ] 10 concurrent requests
- [ ] 50 concurrent requests
- [ ] Check for race conditions
- [ ] Verify data consistency

## Error Handling

### 400 Bad Request
- [ ] Missing required fields
- [ ] Invalid data types
- [ ] Validation errors
- [ ] Clear error messages

### 401 Unauthorized
- [ ] Missing auth token
- [ ] Invalid credentials
- [ ] Expired token

### 404 Not Found
- [ ] Non-existent endpoints
- [ ] Missing resources
- [ ] Deleted users

### 429 Too Many Requests
- [ ] Rate limit exceeded
- [ ] Retry-after header present

### 500 Internal Server Error
- [ ] Database connection failure
- [ ] Unhandled exceptions
- [ ] Should not expose stack traces

## Integration Tests

### User Registration Flow
1. [ ] Register new user
2. [ ] Receive verification code
3. [ ] Verify account
4. [ ] Login successfully
5. [ ] Access protected resources

### Password Reset Flow
1. [ ] Request reset code
2. [ ] Verify code received
3. [ ] Reset password
4. [ ] Login with new password

### Data Sync Flow
1. [ ] Initial data fetch
2. [ ] Incremental updates
3. [ ] Handle conflicts
4. [ ] Verify data integrity

## Post-Test Cleanup
- [ ] Remove test users
- [ ] Clear test transactions
- [ ] Reset rate limits
- [ ] Generate test report

## Test Automation
```bash
# Run all tests
python3 test/test_api_endpoints.py

# Run with coverage
python3 test/test_api_endpoints.py --coverage

# Run specific category
python3 test/test_api_endpoints.py --category auth

# Generate report
python3 test/test_api_endpoints.py --report
```

## Success Criteria
- All endpoints return expected status codes
- Security tests pass (no vulnerabilities)
- Performance meets requirements
- Error messages are helpful
- No sensitive data exposed
- 100% endpoint coverage