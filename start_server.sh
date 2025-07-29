#!/bin/bash
# Madrasha App Server Startup Script
# ==================================

echo "Starting Madrasha App Server..."
echo

# Check if virtual environment exists
if [ ! -f ".venv/bin/python" ]; then
    echo "Error: Virtual environment not found!"
    echo "Please run: python -m venv .venv"
    echo "Then run: .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Check if dev mode is enabled
if [ -f "dev.md" ]; then
    echo "Development mode detected"
    DEV_MODE="--dev"
else
    echo "Production mode"
    DEV_MODE=""
fi

# Start the server
echo "Starting server..."
.venv/bin/python run_server.py $DEV_MODE 