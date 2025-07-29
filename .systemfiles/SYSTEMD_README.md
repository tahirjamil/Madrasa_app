# Madrasa App Systemd Service Setup

This directory contains files to set up the Madrasa app as a systemd service that runs automatically and handles periodic maintenance tasks.

## Files

- `madrasa-app.service` - Systemd service configuration
- `madrasa-app.timer` - Systemd timer for daily restarts
- `setup_systemd.sh` - Automated setup script
- `maintenance.py` - Maintenance script for periodic tasks
- `SYSTEMD_README.md` - This documentation

## Quick Setup

1. **Run the setup script:**
   ```bash
   sudo ./setup_systemd.sh
   ```

2. **Start the service:**
   ```bash
   sudo systemctl start madrasa-app
   sudo systemctl start madrasa-app.timer
   ```

3. **Check status:**
   ```bash
   sudo systemctl status madrasa-app
   sudo systemctl status madrasa-app.timer
   ```

## What the Service Does

### On Startup:
1. **Runs maintenance tasks:**
   - Auto-deletes expired user accounts
   - Creates database backups (if needed)
   - Logs all activities

2. **Starts the server:**
   - Runs your Quart application
   - Handles automatic restarts on failure
   - Logs to systemd journal

### Every 24 Hours:
- **Automatic restart** at 3:00 AM (with 5-minute randomized delay)
- **Fresh maintenance** runs before each restart
- **Clean state** ensures optimal performance

### Security Features:
- Runs as `www-data` user (non-root)
- Restricted file system access
- Protected system directories
- Proper file permissions

## Service Management

### Start/Stop/Restart:
```bash
sudo systemctl start madrasa-app
sudo systemctl stop madrasa-app
sudo systemctl restart madrasa-app
```

### Check Status:
```bash
sudo systemctl status madrasa-app
```

### View Logs:
```bash
# Real-time logs
sudo journalctl -u madrasa-app -f

# Recent logs
sudo journalctl -u madrasa-app -n 50

# Logs since last boot
sudo journalctl -u madrasa-app -b
```

### Enable/Disable Auto-Start:
```bash
sudo systemctl enable madrasa-app    # Start on boot
sudo systemctl disable madrasa-app   # Don't start on boot
```

### Timer Management:
```bash
sudo systemctl enable madrasa-app.timer    # Enable daily restarts
sudo systemctl disable madrasa-app.timer   # Disable daily restarts
sudo systemctl status madrasa-app.timer    # Check timer status
```

## Manual Maintenance

You can run maintenance tasks manually:

```bash
# Run maintenance tasks
python maintenance.py

# Run auto deletion only
python -c "from helpers import delete_users; import asyncio; asyncio.run(delete_users())"

# Run backup only
python database/backup_db.py
```

## Troubleshooting

### Service Won't Start:
1. Check logs: `sudo journalctl -u madrasa-app -n 50`
2. Verify virtual environment exists
3. Check file permissions
4. Ensure MySQL is running

### Permission Issues:
```bash
# Fix permissions
sudo chown -R www-data:www-data /home/tahirjamil/Python/Madrasa_app
sudo chmod -R 755 /home/tahirjamil/Python/Madrasa_app
```

### Virtual Environment Issues:
```bash
# Create virtual environment
cd /home/tahirjamil/Python/Madrasa_app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

### Service File Location:
- `/etc/systemd/system/madrasa-app.service`

### Working Directory:
- `/home/tahirjamil/Python/Madrasa_app`

### User:
- `www-data` (system user)

### Logs:
- Systemd journal (view with `journalctl`)

## Benefits

✅ **Automatic startup** on system boot  
✅ **Automatic restarts** on crashes  
✅ **Daily restarts** at 3:00 AM for fresh state  
✅ **Periodic maintenance** (auto deletion, backups)  
✅ **Proper logging** to systemd journal  
✅ **Security** (non-root user, restricted access)  
✅ **Easy management** with systemctl commands  

## Cron Alternative

If you prefer cron for maintenance instead of systemd:

```bash
# Add to crontab (runs daily at 3 AM)
0 3 * * * cd /home/tahirjamil/Python/Madrasa_app && python maintenance.py

# Add to crontab (runs weekly on Sunday at 4 AM)
0 4 * * 0 cd /home/tahirjamil/Python/Madrasa_app && python maintenance.py
``` 