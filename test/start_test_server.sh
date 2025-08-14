#!/bin/bash
# Start Test Server Script
# ========================
# Starts the Madrasa app server with test configuration

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}Starting Madrasa Test Server${NC}"
echo "================================"

# Set test environment variables
export TEST_MODE=true
export SKIP_ENV_VALIDATION=1

# Set minimal required environment variables for testing
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=test_password
export MYSQL_DB=test_db

export KEYDB_HOST=localhost
export KEYDB_PORT=6379
export KEYDB_PASSWORD=test_password

export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=admin_password

export MADRASA_NAME=test_madrasa
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

export EMAIL_ADDRESS=test@example.com
export EMAIL_PASSWORD=email_password
export TEXTBELT_KEY=test_key

# Additional test configurations
export DUMMY_FULLNAME=test_user
export DUMMY_PHONE=01712345678
export DUMMY_PASSWORD=TestPassword123!
export DUMMY_EMAIL=test@example.com

echo -e "\n${GREEN}Test environment variables set${NC}"
echo "Using SECRET_KEY: ${SECRET_KEY:0:10}..."

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo -e "\n${GREEN}Activating virtual environment${NC}"
    source venv/bin/activate
elif [ -d "test_env" ]; then
    echo -e "\n${GREEN}Activating test environment${NC}"
    source test_env/bin/activate
else
    echo -e "\n${YELLOW}No virtual environment found${NC}"
fi

# Start the server
echo -e "\n${GREEN}Starting server on http://localhost:8000${NC}"
echo "Press Ctrl+C to stop"
echo ""

# Try different ways to start the server
if [ -f "run_server.py" ]; then
    python3 run_server.py
elif [ -f "app.py" ]; then
    python3 -m hypercorn app:app --bind 0.0.0.0:8000
else
    echo -e "${RED}Could not find server entry point!${NC}"
    echo "Please ensure you're in the project root directory"
    exit 1
fi