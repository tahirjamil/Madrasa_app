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