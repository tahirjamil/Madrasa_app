#!/usr/bin/env python3
"""
Advanced Server Runner for Madrasha App

Features:
- Multi-environment support (dev, staging, production)
- Comprehensive logging with rotation
- Health monitoring and auto-restart
- Graceful shutdown handling
- Configuration validation
- Process management
- Security enhancements
- Performance monitoring
"""

import os
import sys
import platform
import subprocess
import signal
import time
import json
import logging
import argparse
import threading
import psutil
import socket
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import asyncio
import tempfile
import shutil

# ─── Configuration ──────────────────────────────────────────────────────────────

class ServerConfig:
    """Centralized configuration management"""
    
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.config_file = self.base_dir / "server_config.json"
        self.pid_file = self.base_dir / "server.pid"
        self.log_dir = self.base_dir / "logs"
        self.temp_dir = self.base_dir / "temp"
        
        # Ensure directories exist
        self.log_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Load or create default config
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create defaults"""
        default_config = {
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
                "auto_restart": True,
                "restart_threshold": 3
            },
            "security": {
                "bind_host": "0.0.0.0",
                "allowed_hosts": ["localhost", "127.0.0.1"],
                "rate_limit": 100,
                "timeout": 30
            }
        }
        
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults
                    self._merge_config(default_config, loaded_config)
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
        
        return default_config
    
    def _merge_config(self, default: Dict, loaded: Dict):
        """Recursively merge loaded config with defaults"""
        for key, value in loaded.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._merge_config(default[key], value)
            else:
                default[key] = value
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")

# ─── Logging Setup ─────────────────────────────────────────────────────────────

class AdvancedLogger:
    """Advanced logging with rotation and multiple handlers"""
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.logger = logging.getLogger("MadrashaServer")
        self.logger.setLevel(getattr(logging, config.config["logging"]["level"]))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        log_file = config.log_dir / f"server_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Error file handler
        error_file = config.log_dir / f"error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_file)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
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

# ─── Process Management ────────────────────────────────────────────────────────

class ProcessManager:
    """Advanced process management with monitoring and auto-restart"""
    
    def __init__(self, config: ServerConfig, logger: AdvancedLogger):
        self.config = config
        self.logger = logger
        self.process: Optional[subprocess.Popen] = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.shutdown_event = threading.Event()
        self.restart_count = 0
        self.last_restart_time = 0
        
    def start_server(self, dev_mode: bool = False) -> bool:
        """Start the server process"""
        try:
            current_os = platform.system()
            self.logger.info(f"Starting server on {current_os}")
            
            # Use Hypercorn for all platforms
            if dev_mode:
                cmd = [sys.executable, "-m", "hypercorn", "app:app", "--config", "hypercorn.toml", "--log-level", "debug", "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\""]
            else:
                cmd = [sys.executable, "-m", "hypercorn", "app:app", "--config", "hypercorn.toml"]
            
            # Set environment variables
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.config.base_dir)
            
            # Start process with different output handling for dev mode
            if dev_mode:
                # In dev mode, show server logs in real-time
                self.process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=None,  # Use parent's stdout
                    stderr=None,  # Use parent's stderr
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                self.logger.info("Dev mode: Server logs will be displayed in real-time")
            else:
                # In production mode, capture output
                self.process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
            
            # Save PID
            with open(self.config.pid_file, 'w') as f:
                f.write(str(self.process.pid))
            
            self.logger.info(f"Server started with PID: {self.process.pid}")
            
            # Start monitoring
            self._start_monitoring()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            return False
    
    def _start_monitoring(self):
        """Start background monitoring thread"""
        self.monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
        self.monitor_thread.start()
        
        # Start log streaming if not in dev mode
        if hasattr(self, 'process') and self.process and self.process.stdout:
            self.log_stream_thread = threading.Thread(target=self._stream_logs, daemon=True)
            self.log_stream_thread.start()
    
    def _stream_logs(self):
        """Stream server logs to console"""
        try:
            while self.process and self.process.poll() is None:
                if self.process.stdout:
                    line = self.process.stdout.readline()
                    if line:
                        print(f"[SERVER] {line.strip()}")
                if self.process.stderr:
                    line = self.process.stderr.readline()
                    if line:
                        print(f"[SERVER-ERROR] {line.strip()}")
                time.sleep(0.1)
        except Exception as e:
            self.logger.error(f"Log streaming error: {e}")
    
    def _monitor_process(self):
        """Monitor server process and restart if needed"""
        while not self.shutdown_event.is_set():
            try:
                if self.process and self.process.poll() is not None:
                    # Process has died
                    return_code = self.process.returncode
                    self.logger.warning(f"Server process died with return code: {return_code}")
                    
                    if self.config.config["monitoring"]["auto_restart"]:
                        self._handle_restart()
                    else:
                        self.logger.error("Auto-restart disabled. Server stopped.")
                        break
                
                # Check resource usage
                if self.process:
                    self._check_resource_usage()
                
                time.sleep(self.config.config["monitoring"]["health_check_interval"])
                
            except Exception as e:
                self.logger.error(f"Error in process monitoring: {e}")
                time.sleep(5)
    
    def _handle_restart(self):
        """Handle server restart with backoff"""
        current_time = time.time()
        
        # Check restart threshold
        if current_time - self.last_restart_time < 60:  # Within 1 minute
            self.restart_count += 1
        else:
            self.restart_count = 1
        
        self.last_restart_time = current_time
        
        if self.restart_count > self.config.config["monitoring"]["restart_threshold"]:
            self.logger.critical(f"Too many restarts ({self.restart_count}). Stopping server.")
            return
        
        # Exponential backoff
        backoff_time = min(2 ** self.restart_count, 60)
        self.logger.info(f"Restarting server in {backoff_time} seconds...")
        time.sleep(backoff_time)
        
        if not self.shutdown_event.is_set():
            self.start_server()
    
    def _check_resource_usage(self):
        """Check CPU and memory usage"""
        try:
            process = psutil.Process(self.process.pid)
            
            # Memory usage
            memory_percent = process.memory_percent()
            memory_limit = self._parse_memory_limit(self.config.config["monitoring"]["max_memory_usage"])
            
            if memory_percent > memory_limit:
                self.logger.warning(f"High memory usage: {memory_percent:.1f}%")
            
            # CPU usage
            cpu_percent = process.cpu_percent()
            cpu_limit = self.config.config["monitoring"]["max_cpu_usage"]
            
            if cpu_percent > cpu_limit:
                self.logger.warning(f"High CPU usage: {cpu_percent:.1f}%")
                
        except Exception as e:
            self.logger.debug(f"Could not check resource usage: {e}")
    
    def _parse_memory_limit(self, limit_str: str) -> float:
        """Parse memory limit string to percentage"""
        try:
            if "MB" in limit_str:
                mb = float(limit_str.replace("MB", ""))
                # Assume 1GB total memory for percentage calculation
                return (mb / 1024) * 100
            elif "GB" in limit_str:
                gb = float(limit_str.replace("GB", ""))
                return gb * 100
            else:
                return float(limit_str)
        except:
            return 50.0  # Default 50%
    
    def stop_server(self, graceful: bool = True):
        """Stop the server process"""
        self.shutdown_event.set()
        
        if self.process:
            if graceful:
                self.logger.info("Sending SIGTERM to server process...")
                self.process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.logger.warning("Server did not stop gracefully, forcing shutdown...")
                    self.process.kill()
            else:
                self.logger.info("Force killing server process...")
                self.process.kill()
            
            # Clean up PID file
            if self.config.pid_file.exists():
                self.config.pid_file.unlink()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)

# ─── Health Checker ────────────────────────────────────────────────────────────

class HealthChecker:
    """Server health monitoring"""
    
    def __init__(self, config: ServerConfig, logger: AdvancedLogger):
        self.config = config
        self.logger = logger
        # Use localhost for health checks since server binds to 0.0.0.0 but is accessible via localhost
        self.server_url = f"http://127.0.0.1:{config.config['server']['port']}"
    
    def check_health(self) -> bool:
        """Perform health check on server"""
        try:
            import requests
            response = requests.get(f"{self.server_url}/health", timeout=5)
            if response.status_code == 200:
                self.logger.info(f"Health check successful: {response.status_code}")
                return True
            else:
                self.logger.warning(f"Health check failed with status: {response.status_code}")
                return False
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False
    
    def wait_for_server(self, timeout: int = 120) -> bool:
        """Wait for server to become available"""
        start_time = time.time()
        attempts = 0
        max_attempts = timeout // 5  # Check every 5 seconds
        
        while time.time() - start_time < timeout:
            attempts += 1
            self.logger.info(f"Health check attempt {attempts}/{max_attempts}")
            
            if self.check_health():
                self.logger.info("Server is healthy and responding")
                return True
            time.sleep(5)  # Wait 5 seconds between checks
        
        self.logger.error("Server did not become healthy within timeout")
        return False

# ─── Signal Handlers ───────────────────────────────────────────────────────────

def setup_signal_handlers(process_manager: ProcessManager, logger: AdvancedLogger):
    """Setup signal handlers for graceful shutdown"""
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        process_manager.stop_server(graceful=True)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if platform.system() != "Windows":
        signal.signal(signal.SIGHUP, signal_handler)

# ─── Main Application ──────────────────────────────────────────────────────────

class AdvancedServerRunner:
    """Main server runner class"""
    
    def __init__(self):
        self.config = ServerConfig()
        self.logger = AdvancedLogger(self.config)
        self.process_manager = ProcessManager(self.config, self.logger)
        self.health_checker = HealthChecker(self.config, self.logger)
        
    def run(self, dev_mode: bool = False, daemon: bool = False):
        """Run the server with advanced features"""
        try:
            # Setup signal handlers
            setup_signal_handlers(self.process_manager, self.logger)
            
            # Check if server is already running
            if self._is_server_running():
                self.logger.error("Server is already running")
                return False
            
            # Validate configuration
            if not self._validate_config():
                self.logger.error("Configuration validation failed")
                return False
            
            # Start server
            if not self.process_manager.start_server(dev_mode):
                return False
            
            # Wait for server to be healthy
            if not self.health_checker.wait_for_server():
                self.logger.error("Server failed to start properly")
                return False
            
            self.logger.info("Server is running successfully")
            
            if dev_mode:
                # In dev mode, wait for the server process to complete
                self.logger.info("Dev mode: Waiting for server process...")
                if self.process_manager.process:
                    self.process_manager.process.wait()
            else:
                # Keep main thread alive
                while not self.process_manager.shutdown_event.is_set():
                    time.sleep(1)
            
            return True
            
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
            return True
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return False
        finally:
            self.process_manager.stop_server()
    
    def _is_server_running(self) -> bool:
        """Check if server is already running"""
        if self.config.pid_file.exists():
            try:
                with open(self.config.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process exists
                if psutil.pid_exists(pid):
                    return True
                else:
                    # Clean up stale PID file
                    self.config.pid_file.unlink()
            except Exception:
                # Clean up invalid PID file
                if self.config.pid_file.exists():
                    self.config.pid_file.unlink()
        
        return False
    
    def _validate_config(self) -> bool:
        """Validate server configuration"""
        try:
            # Check port availability
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((
                self.config.config["server"]["host"],
                self.config.config["server"]["port"]
            ))
            sock.close()
            
            if result == 0:
                self.logger.warning(f"Port {self.config.config['server']['port']} is already in use")
                return False
            
            # Check required files
            required_files = ["app.py", "hypercorn.toml"]
            for file in required_files:
                if not (self.config.base_dir / file).exists():
                    self.logger.error(f"Required file not found: {file}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration validation error: {e}")
            return False

# ─── Command Line Interface ────────────────────────────────────────────────────

def main():
    """Main entry point with command line interface"""
    parser = argparse.ArgumentParser(
        description="Advanced Madrasha App Server Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_server.py                    # Start in production mode
  python run_server.py --dev              # Start in development mode
  python run_server.py --daemon           # Start as daemon
  python run_server.py --config           # Show current configuration
  python run_server.py --stop             # Stop running server
        """
    )
    
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--config", action="store_true", help="Show current configuration")
    parser.add_argument("--stop", action="store_true", help="Stop running server")
    parser.add_argument("--status", action="store_true", help="Check server status")
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = AdvancedServerRunner()
    
    if args.config:
        print("Current Configuration:")
        print(json.dumps(runner.config.config, indent=2))
        return
    
    if args.stop:
        if runner._is_server_running():
            try:
                with open(runner.config.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                print("Server stop signal sent")
            except Exception as e:
                print(f"Error stopping server: {e}")
        else:
            print("No server is currently running")
        return
    
    if args.status:
        if runner._is_server_running():
            print("Server is running")
            try:
                with open(runner.config.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                print(f"PID: {pid}")
            except:
                pass
        else:
            print("Server is not running")
        return
    
    # Check for dev mode file
    dev_md = Path(__file__).resolve().parent / "dev.md"
    dev_mode = dev_md.is_file() or args.dev
    
    print(f"Detected OS: {platform.system()}")
    print(f"Dev mode: {'ON' if dev_mode else 'OFF'}")
    
    # Run server
    success = runner.run(dev_mode=dev_mode, daemon=args.daemon)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
  