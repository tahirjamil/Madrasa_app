#!/usr/bin/env python3
"""
Advanced Server Runner for Madrasha App

"""

import asyncio
import os, sys, platform, subprocess, signal, time, json, logging, argparse, threading, psutil, socket
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from config import server_config as default_config

from utils.helpers.helpers import get_system_health

# ─── Configuration ──────────────────────────────────────────────────────────────

class ServerConfig:
    """Centralized configuration management"""
    
    def __init__(self):
        self.base_dir = Path(__file__).resolve().parent
        self.config_dir = self.base_dir / "config"
        self.pid_file = self.base_dir / "server.pid"
        self.log_dir = self.base_dir / "logs"
        self.temp_dir = self.base_dir / "temp"
        self.hypercorn_config = self.config_dir / "hosting/hypercorn.toml"
        
        # Ensure directories exist
        self.log_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
        
        # Load or create default config
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config file: {e}")
                print("Please check your server_config.json file")
                sys.exit(1)
        else:
            print(f"Config file not found: {self.config_file}")
            print("Please create server_config.json with your configuration")
            sys.exit(1)
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save config: {e}")

server_config = ServerConfig()

# ─── Logging Setup ─────────────────────────────────────────────────────────────

class AdvancedLogger:
    """Advanced logging with rotation and multiple handlers"""
    
    def __init__(self, config: ServerConfig):
        self.config = config
        self.logger = logging.getLogger("MadrashaServer")
        self.logger.setLevel(getattr(logging, default_config.LOGGING_LEVEL))
        
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
        self._lock = threading.Lock()
        self.restart_count = 0
        self.last_restart_time = 0
        self._last_dev_mode = False
        
    def start_server(self, dev_mode: bool = False) -> bool:
        """Start the server process"""
        try:
            with self._lock:
                self._last_dev_mode = dev_mode
            current_os = platform.system()
            self.logger.info(f"Starting server on {current_os}")
            
            # Use Hypercorn for all platforms
            if dev_mode:
                cmd = [sys.executable, "-m", "hypercorn", "app:app", "--config", self.config.hypercorn_config, "--log-level", "debug", "--access-logformat", "%(h)s %(l)s %(u)s %(t)s \"%(r)s\" %(s)s %(b)s \"%(f)s\" \"%(a)s\""]
            else:
                cmd = [sys.executable, "-m", "hypercorn", "app:app", "--config", self.config.hypercorn_config]
            
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
                    
                    if default_config.AUTO_RESTART:
                        self._handle_restart()
                    else:
                        self.logger.error("Auto-restart disabled. Server stopped.")
                        break
                
                time.sleep(default_config.HEALTH_CHECK_INTERVAL)
                
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
        
        if self.restart_count > default_config.RESTART_THRESHOLD:
            self.logger.critical(f"Too many restarts ({self.restart_count}). Stopping server.")
            return
        
        # Exponential backoff
        backoff_time = min(2 ** self.restart_count, 60)
        self.logger.info(f"Restarting server in {backoff_time} seconds...")
        time.sleep(backoff_time)
        
        if not self.shutdown_event.is_set():
            self.start_server()
    
    def stop_server(self, graceful: bool = True, *, for_restart: bool = False):
        """Stop the server process."""
        with self._lock:
            if not for_restart:
                self.shutdown_event.set()
            
            if self.process:
                if graceful:
                    self.logger.info("Sending SIGTERM to server process...")
                    self.process.terminate()
                    
                    # Wait for graceful shutdown
                    try:
                        self.process.wait(timeout=default_config.SERVER_TIMEOUT)
                    except subprocess.TimeoutExpired:
                        self.logger.warning("Server did not stop gracefully, forcing shutdown...")
                        self.process.kill()
                else:
                    self.logger.info("Force killing server process...")
                    self.process.kill()
                
                # Clean up PID file
                if self.config.pid_file.exists():
                    try:
                        self.config.pid_file.unlink()
                    except Exception:
                        self.logger.error("Error cleaning up PID file")
            
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=2)
            
            self.process = None

    def restart_server(self, *, graceful: bool = True) -> bool:
        """Restart the server (graceful or force)."""
        self.logger.info(f"Restart requested ({'graceful' if graceful else 'force'})")
        self.stop_server(graceful=graceful, for_restart=True)
        time.sleep(0.3)
        ok = self.start_server(dev_mode=self._last_dev_mode)
        if ok:
            self.logger.info("Restart completed successfully")
        else:
            self.logger.error("Restart failed")
        return ok

# ─── Signal Handlers ───────────────────────────────────────────────────────────

def setup_signal_handlers(process_manager: ProcessManager, logger: AdvancedLogger):
    """Setup signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        process_manager.stop_server(graceful=True)
        sys.exit(0)

    # Always handle SIGINT & SIGTERM
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Only handle SIGHUP on non-Windows
    if platform.system() != "Windows":
        sighup = getattr(signal, "SIGHUP", None)
        if sighup is not None:
            signal.signal(sighup, signal_handler)

        # Optional restart controls via user signals
        usr1 = getattr(signal, "SIGUSR1", None)
        usr2 = getattr(signal, "SIGUSR2", None)
        if usr1 is not None:
            def _graceful_restart(_s, _f):
                logger.info("Signal SIGUSR1 received: graceful restart")
                process_manager.restart_server(graceful=True)
            signal.signal(usr1, _graceful_restart)
        if usr2 is not None:
            def _force_restart(_s, _f):
                logger.info("Signal SIGUSR2 received: force restart")
                process_manager.restart_server(graceful=False)
            signal.signal(usr2, _force_restart)

# ─── Main Application ──────────────────────────────────────────────────────────

class AdvancedServerRunner:
    """Main server runner class"""
    
    def __init__(self):
        self.config = ServerConfig()
        self.logger = AdvancedLogger(self.config)
        self.process_manager = ProcessManager(self.config, self.logger)
        
    async def run(self, dev_mode: bool = False, daemon: bool = False):
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
            
            # Handle daemon mode
            if daemon:
                self.logger.info("Starting server in daemon mode...")
                if platform.system() != "Windows":
                    # Fork and detach from parent process (Unix-like systems)
                    try:
                        pid = os.fork()
                        if pid > 0:
                            # Parent process - exit
                            self.logger.info(f"Daemon started with PID: {pid}")
                            return True
                        elif pid == 0:
                            # Child process - continue
                            os.setsid()  # Create new session
                            os.umask(0)  # Set file creation mask
                            # Redirect standard file descriptors
                            sys.stdout.flush()
                            sys.stderr.flush()
                            with open(os.devnull, 'r') as f:
                                os.dup2(f.fileno(), sys.stdin.fileno())
                            with open(os.devnull, 'a+') as f:
                                os.dup2(f.fileno(), sys.stdout.fileno())
                                os.dup2(f.fileno(), sys.stderr.fileno())
                    except OSError as e:
                        self.logger.error(f"Failed to fork daemon process: {e}")
                        return False
                else:
                    # Windows - use subprocess with DETACHED_PROCESS flag
                    self.logger.warning("Daemon mode on Windows is limited - using detached process")
            
            # Start server
            if not self.process_manager.start_server(dev_mode):
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
        except SystemExit:
            self.logger.info("Received system exit signal")
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
                default_config.SERVER_HOST,
                default_config.SERVER_PORT
            ))
            sock.close()
            
            if result == 0:
                self.logger.warning(f"Port {default_config.SERVER_PORT} is already in use")
                return False
            
            # Check required files
            required_files = ["app.py", self.config.hypercorn_config]
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
        python run_server.py --stop             # Stop running server
        python run_server.py --status           # Check server status
        python run_server.py --restart          # Gracefully restart running server
        python run_server.py --force-restart    # Force restart running server
        """
    )
    
    parser.add_argument("--dev", action="store_true", help="Run in development mode")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--stop", action="store_true", help="Stop running server")
    parser.add_argument("--status", action="store_true", help="Check server status")
    parser.add_argument("--restart", action="store_true", help="Gracefully restart running server")
    parser.add_argument("--force-restart", action="store_true", help="Force restart running server")
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = AdvancedServerRunner()
    
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

    if args.restart or args.force_restart:
        if runner._is_server_running():
            try:
                with open(runner.config.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                sig = getattr(signal, 'SIGUSR1') if args.restart else getattr(signal, 'SIGUSR2')
                os.kill(pid, sig)
                print("Restart signal sent" + (" (graceful)" if args.restart else " (force)"))
            except Exception as e:
                print(f"Error restarting server: {e}")
        else:
            print("No server is currently running")
        return
    
    # Check for --dev argument
    dev_mode = bool(args.dev)
    
    print(f"Detected OS: {platform.system()}")
    print(f"Dev mode: {'ON' if dev_mode else 'OFF'}")
    print(f"Daemon mode: {'ON' if args.daemon else 'OFF'}")
    
    # Run server
    success = asyncio.run(runner.run(dev_mode=dev_mode, daemon=args.daemon))
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
  