# Madrasa App

A web-based management system for Madrasas, built with Flask and MySQL. The app provides user registration, authentication, payment management, routine scheduling, and admin features.

## Features
- User registration and login
- Admin dashboard
- Payment and transaction management
- Routine and exam scheduling
- Member and people management
- Contact and feedback forms
- Multi-language support

## Tech Stack
- **Backend:** Python, Flask
- **Database:** MySQL
- **Frontend:** Jinja2 templates (HTML/CSS)
- **Other:** PyMySQL, Flask-WTF, Flask-CORS, Waitress

## Project Structure
```
Madrasa_app/
  app.py                # Main Flask app
  config.py             # Configuration
  database/             # DB utilities and backup scripts
  routes/               # Flask Blueprints (user, admin, web)
  static/               # Static files (images, icons)
  templates/            # Jinja2 HTML templates
  uploads/              # Uploaded files
  requirements.txt      # Python dependencies
```

## Setup Instructions
1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd Madrasa_app
   ```
2. **Create a virtual environment and activate it:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables:**
   - Create a `.env` file with secure credentials (see Security section below)
   - **NEVER** use default credentials in production
   
5. **Set up the database:**
   - Ensure MySQL is running and accessible.
   - Create a dedicated database and user for the application.
   - Run the app once to auto-create tables:
     ```bash
     python app.py
     ```
6. **Run the app:**
   ```bash
   python app.py
   # or for production
   python run_server.py
   ```

## Security Configuration

### Required Environment Variables (.env file)
```bash
# Database (REQUIRED - Do not use defaults in production)
MYSQL_HOST=localhost
MYSQL_USER=your_secure_db_user
MYSQL_PASSWORD=your_secure_db_password
MYSQL_DB=your_database_name

# Application Security (REQUIRED)
SECRET_KEY=your_very_long_random_secret_key_here
CSRF_SECRET_KEY=another_different_random_key_here
API_KEY=your_secure_api_key

# Admin Credentials (REQUIRED - Change defaults)
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_very_secure_admin_password

# Application URL
BASE_URL=https://yourdomain.com

# Email Configuration (Optional)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_ADDRESS=your_email@domain.com
EMAIL_PASSWORD=your_email_app_password

# SMS Configuration (Optional)
DEV_PHONE=+8801XXXXXXXXX
MADRASA_PHONE=+8801XXXXXXXXX

# reCAPTCHA (Optional but recommended)
RECAPTCHA_SITE_KEY=your_recaptcha_site_key
RECAPTCHA_SECRET_KEY=your_recaptcha_secret_key

# SSL/Security (for production)
SESSION_SECURE=true
```

### Security Features Implemented
- **CSRF Protection**: All forms protected against Cross-Site Request Forgery
- **SQL Injection Prevention**: All database queries use parameterized statements
- **Session Security**: Secure session configuration with timeouts
- **Rate Limiting**: SMS/Email verification rate limiting
- **Input Validation**: Comprehensive input sanitization
- **Security Headers**: XSS protection, content type sniffing prevention
- **Device Validation**: Unknown device detection and blocking
- **Password Security**: Proper password hashing with Werkzeug 

## Usage
- Access the app at `http://localhost:8000` (or your configured port).
- Admin dashboard: `/admin`
- User registration and login: `/register`, `/login`
- Payment endpoints: `/due_payment`, `/pay_sslcommerz`, etc.

## Contribution
1. Fork the repository
2. Create a new branch (`git checkout -b feature-branch`)
3. Commit your changes
4. Push to your fork and open a Pull Request

## License
This project is licensed under the MIT License. 

## Deploying with Nginx and Gunicorn

For production, it is recommended to use Nginx as a reverse proxy in front of Gunicorn. Nginx will serve static files and the favicon directly for best performance, and proxy all other requests to Gunicorn.

### 1. Gunicorn
Start your Flask app with Gunicorn (example with 4 workers):

```bash
pip install gunicorn
python run_server.py  # or manually:
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

### 2. Nginx
Use the provided `nginx.conf` as a template. Update the following line to the absolute path of your project's static directory:

```
    alias   /absolute/path/to/your/project/static/;
```

Place the config in `/etc/nginx/sites-available/yourapp` and symlink it to `/etc/nginx/sites-enabled/`:

```bash
sudo ln -s /etc/nginx/sites-available/yourapp /etc/nginx/sites-enabled/
sudo nginx -t  # test config
sudo systemctl reload nginx
```

- Nginx will serve `/static/` and `/favicon.ico` directly.
- All other requests are proxied to Gunicorn at `http://127.0.0.1:8000`.

See `nginx.conf` in this repo for a full example. 

### 3. Enabling HTTPS with Let's Encrypt

For secure HTTPS, you can use a free SSL certificate from [Let's Encrypt](https://letsencrypt.org/) with Certbot.

#### Steps:
1. **Install Certbot:**
   ```bash
   sudo apt update
   sudo apt install certbot python3-certbot-nginx
   ```
2. **Obtain and install a certificate:**
   Replace `yourdomain.com` with your actual domain name.
   ```bash
   sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
   ```
   Certbot will automatically update your Nginx config and reload Nginx.

3. **Sample SSL server block:**
   If you want to manually edit your config, add the following to your `nginx.conf`:
   ```nginx
   server {
       listen 443 ssl;
       server_name yourdomain.com www.yourdomain.com;

       ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
       include /etc/letsencrypt/options-ssl-nginx.conf;
       ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

       # ... (static, favicon, and proxy config as above) ...
   }

   # Redirect HTTP to HTTPS
   server {
       listen 80;
       server_name yourdomain.com www.yourdomain.com;
       return 301 https://$host$request_uri;
   }
   ```

4. **Auto-renewal:**
   Certbot sets up auto-renewal. You can test renewal with:
   ```bash
   sudo certbot renew --dry-run
   ```

For more details, see the [Certbot documentation](https://certbot.eff.org/). 


# Advanced Madrasha App Server Runner

## Overview

The advanced server runner (`run_server.py`) is a production-ready, robust server launcher with comprehensive monitoring, health checks, and graceful shutdown capabilities. It replaces the basic server runner with enterprise-grade features.

## Features

### 🔧 **Advanced Configuration Management**
- JSON-based configuration system
- Environment-specific settings
- Runtime configuration validation
- Hot-reload capability (planned)

### 📊 **Comprehensive Monitoring**
- Real-time health checks
- Resource usage monitoring (CPU, Memory)
- Process lifecycle management
- Auto-restart with exponential backoff
- Performance metrics collection

### 🛡️ **Robust Error Handling**
- Graceful shutdown handling
- Signal management (SIGINT, SIGTERM, SIGHUP)
- Exception recovery
- Process isolation

### 📝 **Advanced Logging**
- Multi-level logging (Console, File, Error)
- Log rotation and retention
- Structured logging format
- Debug and production modes

### 🔄 **Process Management**
- PID file management
- Process monitoring
- Auto-restart capabilities
- Resource limit enforcement

### 🚀 **Production Ready**
- Daemon mode support
- SSL/TLS configuration
- Security headers
- Rate limiting
- Load balancing ready

## Usage

### Basic Commands

```bash
# Start server in production mode
python run_server.py

# Start server in development mode
python run_server.py --dev

# Start as daemon
python run_server.py --daemon

# Check server status
python run_server.py --status

# Stop running server
python run_server.py --stop

# Show current configuration
python run_server.py --config
```

### Environment Detection

The server automatically detects:
- **Operating System**: Windows, Linux, macOS
- **Development Mode**: Presence of `dev.md` file
- **Configuration**: `server_config.json` file

## Configuration

### Server Configuration (`server_config.json`)

```json
{
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "workers": 1,
    "timeout": 60,
    "max_requests": 1000,
    "max_requests_jitter": 50
  },
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "rotation": "1 day",
    "retention": "30 days",
    "max_size": "10MB"
  },
  "monitoring": {
    "health_check_interval": 30,
    "max_memory_usage": "512MB",
    "max_cpu_usage": 80,
    "auto_restart": true,
    "restart_threshold": 3
  },
  "security": {
    "bind_host": "0.0.0.0",
    "allowed_hosts": ["localhost", "127.0.0.1"],
    "rate_limit": 100,
    "timeout": 30
  }
}
```

### Hypercorn Configuration (`hypercorn.toml`)

```toml
# Server Binding
bind = ["0.0.0.0:8000"]
backlog = 2048

# Worker Configuration
workers = 1
worker_class = "asyncio"
worker_connections = 1000

# Timeouts
timeout = 60
keep_alive = 5
graceful_timeout = 30

# Security Settings
limit_concurrency = 1000
limit_max_requests = 1000
limit_max_requests_jitter = 50
```

## Health Monitoring

### Health Check Endpoint

The server provides a `/health` endpoint that returns:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00",
  "version": "1.0.0",
  "uptime": 3600,
  "database": "connected",
  "maintenance_mode": false
}
```

### Monitoring Features

- **Resource Monitoring**: CPU and memory usage tracking
- **Process Health**: Automatic detection of process failures
- **Database Connectivity**: Database connection status
- **Auto-Restart**: Intelligent restart with backoff strategy

## Logging

### Log Files

- `logs/server_YYYYMMDD.log`: General server logs
- `logs/error_YYYYMMDD.log`: Error-specific logs
- `hypercorn.log`: Hypercorn server logs

### Log Levels

- **DEBUG**: Detailed debugging information
- **INFO**: General operational messages
- **WARNING**: Warning conditions
- **ERROR**: Error conditions
- **CRITICAL**: Critical errors

## Security Features

### Built-in Security

- **CSRF Protection**: Automatic CSRF token generation and validation
- **Security Headers**: XSS protection, content type sniffing prevention
- **Rate Limiting**: Request rate limiting capabilities
- **Input Validation**: Comprehensive input sanitization

### SSL/TLS Support

To enable SSL/TLS, uncomment and configure in `hypercorn.toml`:

```toml
certfile = "path/to/cert.pem"
keyfile = "path/to/key.pem"
```

## Performance Optimization

### Resource Limits

- **Memory Usage**: Configurable memory limits
- **CPU Usage**: CPU usage monitoring and limits
- **Connection Limits**: Maximum concurrent connections
- **Request Limits**: Maximum requests per worker

### Optimization Features

- **Worker Processes**: Multi-worker support
- **Connection Pooling**: Database connection pooling
- **Caching**: Response caching capabilities
- **Compression**: Response compression

## Troubleshooting

### Common Issues

1. **Port Already in Use**
   ```bash
   # Check what's using the port
   netstat -tulpn | grep :8000
   
   # Kill the process
   kill -9 <PID>
   ```

2. **Permission Denied**
   ```bash
   # Check file permissions
   ls -la run_server.py
   
   # Make executable
   chmod +x run_server.py
   ```

3. **Database Connection Issues**
   ```bash
   # Check database status
   python run_server.py --status
   
   # Check logs
   tail -f logs/error_$(date +%Y%m%d).log
   ```

### Debug Mode

Enable debug mode for detailed logging:

```bash
# Set environment variable
export LOG_LEVEL=DEBUG

# Or modify server_config.json
{
  "logging": {
    "level": "DEBUG"
  }
}
```

## Deployment

### Production Deployment

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   cp server_config.json.example server_config.json
   # Edit configuration
   ```

3. **Start Server**
   ```bash
   python run_server.py --daemon
   ```

4. **Monitor**
   ```bash
   python run_server.py --status
   tail -f logs/server_$(date +%Y%m%d).log
   ```

### Systemd Service (Linux)

Create `/etc/systemd/system/madrasha-app.service`:

```ini
[Unit]
Description=Madrasha App Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/madrasha-app
ExecStart=/path/to/venv/bin/python run_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable madrasha-app
sudo systemctl start madrasha-app
sudo systemctl status madrasha-app
```

## API Reference

### Command Line Options

| Option | Description |
|--------|-------------|
| `--dev` | Run in development mode |
| `--daemon` | Run as daemon process |
| `--config` | Show current configuration |
| `--stop` | Stop running server |
| `--status` | Check server status |

### Configuration Options

| Section | Key | Description | Default |
|---------|-----|-------------|---------|
| server | host | Server host | 0.0.0.0 |
| server | port | Server port | 8000 |
| server | workers | Number of workers | 1 |
| monitoring | health_check_interval | Health check interval (seconds) | 30 |
| monitoring | max_memory_usage | Maximum memory usage | 512MB |
| monitoring | auto_restart | Enable auto-restart | true |

## Contributing

### Development Setup

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd madrasha-app
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run in Development Mode**
   ```bash
   touch dev.md  # Enable dev mode
   python run_server.py --dev
   ```

### Testing

```bash
# Run health check
curl http://localhost:8000/health

# Check server status
python run_server.py --status

# Test graceful shutdown
python run_server.py --stop
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Check the logs in `logs/` directory
- Review the configuration in `server_config.json` 