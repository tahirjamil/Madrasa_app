import platform
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Use the venv's gunicorn if it exists
HYPERCORN_PATH = str(BASE_DIR / "venv" / "bin" / "hypercorn")

WINDOWS_CMD = [sys.executable, "app.py"]

HYPERCORN_CMD = ["hypercorn", "app:app", "--config", "hypercorn.toml"]
HYPERCORN_CMD_DEBUG = HYPERCORN_CMD + ["--log-level", "debug"]
LINUX_CMD = [HYPERCORN_PATH, "app:app", "--config", "hypercorn.toml"]
LINUX_CMD_DEBUG = LINUX_CMD + ["--log-level", "debug"]

DEV_MD = BASE_DIR / "dev.md"

def main():
    current_os = platform.system()
    dev_mode = DEV_MD.is_file()
    print(f"Detected OS: {current_os}")
    print(f"Dev mode: {'ON' if dev_mode else 'OFF'}")
    try:
        if current_os == "Windows":
            print("Starting server using app.py (Quart dev server)...")
            subprocess.run(WINDOWS_CMD, check=True)
        else:
            if dev_mode:
                print("Starting server using Hypercorn (debug mode, logs to terminal)...")
                try:
                    subprocess.run(HYPERCORN_CMD_DEBUG, check=True)
                except FileNotFoundError as e:
                    subprocess.run(LINUX_CMD_DEBUG, check=True)
            else:
                print("Starting server using Hypercorn (production mode, logs to hypercorn.log)...")
                with open("hypercorn.log", "a") as logfile:
                    try:
                        subprocess.run(HYPERCORN_CMD, stdout=logfile, stderr=logfile, check=True)
                    except FileNotFoundError as e:
                        subprocess.run(LINUX_CMD, stdout=logfile, stderr=logfile, check=True)
                print("Logs are being written to hypercorn.log")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        if current_os != "Windows":
            print("Hypercorn not found. Please install it with: pip install hypercorn")

    except subprocess.CalledProcessError as e:
        print(f"Server process exited with error: {e}")
    except KeyboardInterrupt:
        print("\nServer stopped by user (Ctrl+C).")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()