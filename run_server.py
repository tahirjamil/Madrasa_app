import platform
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Use the venv's gunicorn if it exists
GUNICORN_PATH = str(BASE_DIR / "venv" / "bin" / "gunicorn")

WINDOWS_CMD = [sys.executable, "app.py"]
LINUX_CMD = [GUNICORN_PATH, "-w", "4", "-b", "0.0.0.0:80", "app:app"]
LINUX_CMD_DEBUG = LINUX_CMD + ["--log-level", "debug"]

DEV_MD = BASE_DIR / "dev.md"

def main():
    current_os = platform.system()
    dev_mode = DEV_MD.is_file()
    print(f"Detected OS: {current_os}")
    print(f"Dev mode: {'ON' if dev_mode else 'OFF'}")
    try:
        if current_os == "Windows":
            print("Starting server using app.py (Waitress/Flask dev server)...")
            subprocess.run(WINDOWS_CMD, check=True)
        else:
            if not dev_mode:
                print("Starting server using Gunicorn (debug mode, logs to terminal)...")
                print("If you don't have Gunicorn installed, run: pip install gunicorn")
                subprocess.run(LINUX_CMD_DEBUG, check=True)
            else:
                print("Starting server using Gunicorn (production mode, logs to gunicorn.log)...")
                print("If you don't have Gunicorn installed, run: pip install gunicorn")
                with open("gunicorn.log", "a") as logfile:
                    subprocess.run(LINUX_CMD, stdout=logfile, stderr=logfile, check=True)
                print("Logs are being written to gunicorn.log")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        if current_os != "Windows":
            print("Gunicorn not found. Please install it with: pip install gunicorn")
    except subprocess.CalledProcessError as e:
        print(f"Server process exited with error: {e}")
    except KeyboardInterrupt:
        print("\nServer stopped by user (Ctrl+C).")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()