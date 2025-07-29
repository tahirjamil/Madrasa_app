#!/bin/bash

# Madrasa App Systemd Service Setup Script
# This script installs and configures the systemd service for the Madrasa app

set -e

echo "🔧 Madrasa App Systemd Service Setup"
echo "====================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root (use sudo)"
   exit 1
fi

# Get the project directory
PROJECT_DIR="/home/tahirjamil/Python/Madrasa_app"
SERVICE_FILE="madrasa-app.service"
TIMER_FILE="madrasa-app.timer"

echo "📁 Project Directory: $PROJECT_DIR"
echo "📄 Service File: $SERVICE_FILE"
echo "⏰ Timer File: $TIMER_FILE"
echo

# Check if project directory exists
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "❌ Project directory not found: $PROJECT_DIR"
    echo "   Please update the PROJECT_DIR variable in this script"
    exit 1
fi

# Check if service file exists
if [[ ! -f "$SERVICE_FILE" ]]; then
    echo "❌ Service file not found: $SERVICE_FILE"
    exit 1
fi

# Check if timer file exists
if [[ ! -f "$TIMER_FILE" ]]; then
    echo "❌ Timer file not found: $TIMER_FILE"
    exit 1
fi

# Check if virtual environment exists
VENV_PATH="$PROJECT_DIR/venv"
if [[ ! -d "$VENV_PATH" ]]; then
    echo "⚠️  Virtual environment not found at: $VENV_PATH"
    echo "   Please create a virtual environment first:"
    echo "   cd $PROJECT_DIR && python3 -m venv venv"
    echo "   source venv/bin/activate && pip install -r requirements.txt"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Create www-data user if it doesn't exist
if ! id "www-data" &>/dev/null; then
    echo "👤 Creating www-data user..."
    useradd -r -s /bin/false www-data
fi

# Set proper permissions
echo "🔐 Setting permissions..."
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"
chmod 644 "$PROJECT_DIR"/*.py
chmod 644 "$PROJECT_DIR"/*.txt
chmod 644 "$PROJECT_DIR"/*.toml
chmod 644 "$PROJECT_DIR"/*.cfg

# Create necessary directories with proper permissions
mkdir -p "$PROJECT_DIR/uploads"
mkdir -p "$PROJECT_DIR/database/backups"
chown -R www-data:www-data "$PROJECT_DIR/uploads"
chown -R www-data:www-data "$PROJECT_DIR/database/backups"
chmod -R 755 "$PROJECT_DIR/uploads"
chmod -R 755 "$PROJECT_DIR/database/backups"

# Copy service file to systemd directory
echo "📋 Installing systemd service..."
cp "$SERVICE_FILE" /etc/systemd/system/

# Copy timer file to systemd directory
echo "⏰ Installing systemd timer..."
cp "$TIMER_FILE" /etc/systemd/system/

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Enable the service
echo "✅ Enabling service..."
systemctl enable madrasa-app.service

# Enable the timer
echo "⏰ Enabling timer..."
systemctl enable madrasa-app.timer

echo
echo "🎉 Setup complete!"
echo
echo "📋 Service Status:"
echo "   Status: $(systemctl is-active madrasa-app.service)"
echo "   Enabled: $(systemctl is-enabled madrasa-app.service)"
echo "   Timer: $(systemctl is-enabled madrasa-app.timer)"
echo
echo "🔧 Useful Commands:"
echo "   Start:   sudo systemctl start madrasa-app"
echo "   Stop:    sudo systemctl stop madrasa-app"
echo "   Restart: sudo systemctl restart madrasa-app"
echo "   Status:  sudo systemctl status madrasa-app"
echo "   Logs:    sudo journalctl -u madrasa-app -f"
echo "   Timer:   sudo systemctl status madrasa-app.timer"
echo
echo "🚀 To start the service now, run:"
echo "   sudo systemctl start madrasa-app"
echo
echo "📝 To view logs:"
echo "   sudo journalctl -u madrasa-app -f" 