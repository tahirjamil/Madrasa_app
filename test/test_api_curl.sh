#!/bin/bash
# API Testing with CURL Commands
# ==============================
# Tests all API endpoints using curl for manual testing

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base URL
BASE_URL="${1:-http://localhost:8000}"
echo -e "${BLUE}Testing API at: $BASE_URL${NC}\n"

# Test data
PHONE="01712345678"
PASSWORD="TestPass123!"
FULLNAME="test_user"
EMAIL="test@example.com"

# Function to print test header
print_header() {
    echo -e "\n${YELLOW}=== $1 ===${NC}"
}

# Function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4
    
    echo -e "\n${BLUE}Testing: $description${NC}"
    echo "Endpoint: $method $endpoint"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$BASE_URL$endpoint")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint")
    fi
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -n1)
    # Extract body (all but last line)
    body=$(echo "$response" | sed '$d')
    
    if [[ $status_code -ge 200 && $status_code -lt 300 ]]; then
        echo -e "${GREEN}✓ Success (Status: $status_code)${NC}"
    else
        echo -e "${RED}✗ Failed (Status: $status_code)${NC}"
    fi
    
    # Pretty print JSON if possible
    if command -v jq &> /dev/null; then
        echo "$body" | jq '.' 2>/dev/null || echo "$body"
    else
        echo "$body"
    fi
}

# 1. Test Web Routes
print_header "Testing Web Routes"

test_endpoint "GET" "/" "" "Home page"
test_endpoint "GET" "/donate" "" "Donate page"
test_endpoint "GET" "/contact" "" "Contact page"
test_endpoint "GET" "/privacy" "" "Privacy page"
test_endpoint "GET" "/terms" "" "Terms page"

# 2. Test Authentication Flow
print_header "Testing Authentication Flow"

# Register
test_endpoint "POST" "/register" '{
    "fullname": "'$FULLNAME'",
    "phone": "'$PHONE'",
    "password": "'$PASSWORD'",
    "email": "'$EMAIL'",
    "device_id": "test_device",
    "ip_address": "192.168.1.1"
}' "User Registration"

# Login
test_endpoint "POST" "/login" '{
    "phone": "'$PHONE'",
    "password": "'$PASSWORD'",
    "device_id": "test_device"
}' "User Login"

# Send verification code
test_endpoint "POST" "/send_code" '{
    "phone": "'$PHONE'"
}' "Send Verification Code"

# Account check
test_endpoint "POST" "/account/check" '{
    "phone": "'$PHONE'"
}' "Account Check"

# 3. Test Data Endpoints
print_header "Testing Data Endpoints"

test_endpoint "POST" "/members" '{
    "updatedSince": null
}' "Get Members"

test_endpoint "POST" "/routines" '{
    "updatedSince": null
}' "Get Routines"

test_endpoint "POST" "/events" '{
    "updatedSince": null
}' "Get Events"

test_endpoint "POST" "/exams" '{
    "updatedSince": null
}' "Get Exams"

# 4. Test Payment Endpoints
print_header "Testing Payment Endpoints"

test_endpoint "POST" "/due_payments" '{
    "phone": "'$PHONE'",
    "fullname": "'$FULLNAME'"
}' "Get Due Payments"

test_endpoint "POST" "/get_transactions" '{
    "phone": "'$PHONE'",
    "fullname": "'$FULLNAME'"
}' "Get Transactions"

# 5. Test Error Handling
print_header "Testing Error Handling"

# Missing fields
test_endpoint "POST" "/register" '{
    "phone": "'$PHONE'"
}' "Registration with Missing Fields"

# Invalid data
test_endpoint "POST" "/register" '{
    "fullname": "a",
    "phone": "invalid",
    "password": "weak",
    "email": "not-email"
}' "Registration with Invalid Data"

# SQL Injection attempt
test_endpoint "POST" "/login" '{
    "phone": "'\'' OR '\''1'\''='\''1",
    "password": "'\'' OR '\''1'\''='\''1"
}' "SQL Injection Test"

# XSS attempt
test_endpoint "POST" "/add_people" '{
    "name_en": "<script>alert('\''xss'\'')</script>",
    "phone": "01712345678",
    "acc_type": "student"
}' "XSS Protection Test"

# 6. Test File Endpoints
print_header "Testing File Endpoints"

test_endpoint "GET" "/uploads/profile_img/test.jpg" "" "Profile Image (404 expected)"
test_endpoint "GET" "/uploads/notices/test.pdf" "" "Notice File (404 expected)"
test_endpoint "GET" "/uploads/exam_results/test.pdf" "" "Exam Result (404 expected)"

# 7. Test Rate Limiting
print_header "Testing Rate Limiting"

echo -e "\nSending multiple requests to test rate limiting..."
for i in {1..12}; do
    echo -n "Request $i: "
    status=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        -H "Content-Type: application/json" \
        -d '{"phone": "'$PHONE'"}' \
        "$BASE_URL/send_code")
    
    if [ "$status" = "429" ]; then
        echo -e "${GREEN}Rate limit triggered (429)${NC}"
        break
    else
        echo "Status: $status"
    fi
    
    # Small delay between requests
    sleep 0.1
done

# Summary
echo -e "\n${YELLOW}======================================${NC}"
echo -e "${YELLOW}         TEST COMPLETE                ${NC}"
echo -e "${YELLOW}======================================${NC}"
echo -e "\nNote: Install 'jq' for better JSON formatting:"
echo "  Ubuntu/Debian: sudo apt-get install jq"
echo "  macOS: brew install jq"
