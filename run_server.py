#!/usr/bin/env python3
"""
Docker-Friendly Server Runner for Madrasha App

Simplified for Docker containers - Docker handles process management,
restarts, health checks, and daemon mode.
"""

import asyncio
import os
import sys
import signal
import logging
from datetime import datetime
from pathlib import Path

from config import server_config as default_config, config as global_config

# ─── Configuration ──────────────────────────────────────────────────────────────

class ServerConfig:
    """Simple configuration for Docker environment"""
    
    def __init__(self):
        self.base_dir = global_config.get_project_root()
        self.log_dir = self.base_dir / "logs"
        
        # Ensure log directory exists
        self.log_dir.mkdir(exist_ok=True)

# ─── Logging Setup ─────────────────────────────────────────────────────────────

class DockerLogger:
    """Docker-friendly logging - outputs to stdout/stderr for container logs"""
    
    def __init__(self, config: ServerConfig):
        self.logger = logging.getLogger("MadrashaServer")
        self.logger.setLevel(getattr(logging, default_config.LOGGING_LEVEL.upper()))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Console handler for Docker logs (stdout/stderr)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # Error handler (stderr)
        error_handler = logging.StreamHandler(sys.stderr)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)
    
    def info(self, message: str):
        self.logger.info(message)
    
    def error(self, message: str):
        self.logger.error(message)
    
    def warning(self, message: str):
        self.logger.warning(message)
    
    def debug(self, message: str):
        self.logger.debug(message)
    
    def critical(self, message: str):
        self.logger.critical(message)

# ─── Docker-Friendly Server Runner ────────────────────────────────────────────

class DockerServerRunner:
    """Simplified server runner for Docker containers"""
    
    def __init__(self):
        self.config = ServerConfig()
        self.logger = DockerLogger(self.config)
        self.shutdown_requested = False
        
    def setup_signal_handlers(self):
        """Setup simple signal handlers for Docker"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.shutdown_requested = True
        
        # Docker sends SIGTERM for graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    
    def get_server_config(self):
        """Get server configuration from environment"""
        # Docker-friendly configuration via environment variables
        host = os.getenv("HOST", default_config.SERVER_HOST)
        port = int(os.getenv("PORT", default_config.SERVER_PORT))
        workers = int(os.getenv("WORKERS", default_config.SERVER_WORKERS))
        log_level = os.getenv("LOG_LEVEL", getattr(default_config, 'LOGGING_LEVEL', 'info')).lower()
        reload = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
        
        return {
            "host": host,
            "port": port,
            "workers": workers,
            "log_level": log_level,
            "reload": reload
        }
    
    def validate_environment(self):
        """Basic environment validation for Docker"""
        try:
            # Check if main.py exists
            app_file = self.config.base_dir / "app" /"main.py"
            if not app_file.exists():
                self.logger.error("app.py not found")
                return False
            
            # Check if we're in Docker
            is_docker = os.path.exists('/.dockerenv')
            if is_docker:
                self.logger.info("Running in Docker container")
            else:
                self.logger.info("Running in local environment")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Environment validation failed: {e}")
            return False
    
    async def run(self):
        """Run the server with Docker-friendly configuration"""
        try:
            self.logger.info("Starting Madrasha FastAPI server...")
            
            # Setup signal handlers
            self.setup_signal_handlers()
            
            # Validate environment
            if not self.validate_environment():
                return False
            
            # Get configuration
            config = self.get_server_config()
            self.logger.info(f"Server config: {config}")
            
            # Import and run uvicorn
            import uvicorn
            
            # Create uvicorn config
            uvicorn_config = {
                "app": "app.main:app",
                "host": config["host"],
                "port": config["port"],
                "log_level": config["log_level"],
                "access_log": True,
                "use_colors": False,  # Better for Docker logs
                "server_header": False,  # Security
                "date_header": False,   # Security
            }
            
            # Add reload or workers based on environment
            if config["reload"]:
                self.logger.info("Starting in development mode with auto-reload")
                uvicorn_config["reload"] = True
            else:
                self.logger.info(f"Starting in production mode with {config['workers']} workers")
                uvicorn_config["workers"] = config["workers"]
            
            # Run the server
            server = uvicorn.Server(uvicorn.Config(**uvicorn_config))
            
            self.logger.info(f"Server starting on {config['host']}:{config['port']}")
            await server.serve()
            
            return True
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt")
            return True
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            return False

# ─── Main Entry Point ──────────────────────────────────────────────────────────

async def main():
    """Main entry point for Docker"""
    runner = DockerServerRunner()
    
    # Determine mode
    dev_mode = global_config.is_development()
    
    runner.logger.info("=== Madrasha FastAPI Server ===")
    runner.logger.info(f"Environment: {'Development' if dev_mode else 'Production'}")
    runner.logger.info(f"Python: {sys.version}")
    
    # Run server
    success = await runner.run()
    
    runner.logger.info("Server shutdown complete")
    return success

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Failed to start server: {e}")
        sys.exit(1)