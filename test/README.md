# User Routes Integration Tests

This directory contains integration tests for the user routes that test the actual API endpoints by connecting to a running server.

## Files

- `test_user_routes.py` - Main integration test file
- `start_server_for_testing.py` - Script to start the server for testing
- `README.md` - This file

## How to Use

### 1. Start the Server

First, start the server for testing:

```bash
# Option 1: Use the test script
python test/start_server_for_testing.py

# Option 2: Start manually
python run_server.py
```

The server should be running on `http://localhost:8000`

### 2. Run the Integration Tests

In a new terminal, run the integration tests:

```bash
python test/test_user_routes.py
```

## Test Coverage

The integration tests cover all user routes:

### Authentication Routes
- ✅ `/register` - User registration
- ✅ `/login` - User login
- ✅ `/send_code` - Send verification code
- ✅ `/reset_password` - Password reset

### Core Routes
- ✅ `/add_people` - Add person
- ✅ `/members` - Get members
- ✅ `/routines` - Get routines
- ✅ `/events` - Get events
- ✅ `/exams` - Get exams

### Account Management
- ✅ `/account/deactivate` - Account deactivation
- ✅ `/account/check` - Account status check

### File Serving
- ✅ `/static/user_profile_img/<filename>` - Profile images
- ✅ `/uploads/notices/<filename>` - Notice files
- ✅ `/uploads/exam_results/<filename>` - Exam result files
- ✅ `/uploads/madrasa_pictures/<gender>/<folder>/<filename>` - Madrasa pictures

### Error Handling
- ✅ Invalid data handling
- ✅ Missing required fields
- ✅ Server connection errors

## Test Data

The tests use dummy data that includes:

```python
dummy_data = {
    "fullname": "test_user",
    "phone": "01712345678",
    "password": "TestPassword123!",
    "email": "test@example.com",
    "code": "123456",
    "device_id": "test_device_123",
    "ip_address": "192.168.1.100"
}
```

## Test Mode

The tests run in test mode, which means:
- No actual SMS/email sending
- No real database operations
- Dummy responses for certain operations
- Environment variables are set automatically

## Expected Results

### When Server is Running
- ✅ All tests should pass
- ✅ Proper HTTP status codes (200, 201, 400, etc.)
- ✅ JSON responses with expected structure

### When Server is Not Running
- ⚠️ Tests will show "Server not running" warnings
- ⚠️ Tests will be marked as failed but not as errors
- ⚠️ This is expected behavior for integration tests

## Troubleshooting

### Server Connection Issues
1. Make sure the server is running on `http://localhost:8000`
2. Check if the port is not blocked by firewall
3. Verify the server started without errors

### Test Failures
1. Check server logs for errors
2. Verify database connection
3. Ensure all required environment variables are set

### Environment Issues
1. Make sure all dependencies are installed:
   ```bash
   pip install aiohttp
   ```
2. Verify Python path includes the project root
3. Check that all required modules can be imported

## Running Specific Tests

You can modify the test file to run only specific tests by commenting out the unwanted tests in the `run_all_tests` method.

## Adding New Tests

To add new route tests:

1. Add a new async method to `TestUserRoutesIntegration`
2. Use the pattern:
   ```python
   async def test_new_route(self):
       try:
           async with self.session.post(
               f"{self.base_url}/new_route",
               json=test_data
           ) as response:
               data = await response.json()
               result = {
                   "test": "new_route",
                   "status": response.status,
                   "success": response.status == expected_status,
                   "message": data.get('message', 'Unknown'),
                   "data": data
               }
               self.test_results.append(result)
               print(f"✅ New route test: {result['message']}")
               return result
       except aiohttp.ClientConnectorError:
           # Handle server not running
           return result
   ```

3. Add the test to the `run_all_tests` method

## Output Format

The tests provide detailed output including:
- Test name and status
- HTTP status codes
- Response messages
- Success/failure indicators
- Summary statistics

Example output:
```
🧪 Running User Routes Integration Tests...
============================================================
Note: Make sure the server is running on http://localhost:8000
============================================================
✅ Register route test: Registration successful
✅ Login route test: Login successful
✅ Send verification code route test: Verification code sent
...

============================================================
📊 Integration Test Summary:
   Tests run: 13
   Successful: 13
   Failed: 0
✅ All integration tests passed!
``` 