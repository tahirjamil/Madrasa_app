import os, subprocess, glob
from datetime import datetime, timezone, timedelta
from logger import log_event_async as log_event
from config import Config

# ======= Configuration ========
DB_NAME = Config.MYSQL_DB
DB_USER = Config.MYSQL_USER
DB_PASSWORD = Config.MYSQL_PASSWORD
MAX_DAILY_BACKUPS = 7
MAX_WEEKLY_BACKUPS = 20

# ======= Paths ========
BASE_DIR = os.path.dirname(__file__)
DAILY_BACKUP_DIR = os.path.join(BASE_DIR, "backups", "daily")
WEEKLY_BACKUP_DIR = os.path.join(BASE_DIR, "backups", "weekly")
os.makedirs(DAILY_BACKUP_DIR, exist_ok=True)
os.makedirs(WEEKLY_BACKUP_DIR, exist_ok=True)

def get_last_backup_time(backup_dir):
    """Find the most recent backup file and return its creation time"""
    backup_files = glob.glob(os.path.join(backup_dir, f"{DB_NAME}_backup_*.sql"))
    if not backup_files:
        return datetime.min.replace(tzinfo=timezone.utc)
    
    # Get the most recent file by modification time
    latest_file = max(backup_files, key=os.path.getmtime)
    return datetime.fromtimestamp(os.path.getmtime(latest_file), tz=timezone.utc)

def create_backup(backup_path):
    """Create a database backup using mysqldump"""
    dump_command = [
        "mysqldump",
        "-u", DB_USER,
        f"-p{DB_PASSWORD}",
        "--single-transaction",  # Consistent backup
        "--routines",           # Include stored procedures
        "--triggers",          # Include triggers
        "--events",            # Include events
        DB_NAME,
    ]
    
    try:
        with open(backup_path, "w") as f:
            result = subprocess.run(
                dump_command, 
                stdout=f, 
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e}")
        print(f"Error output: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error during backup: {e}")
        return False

def cleanup_old_backups(backup_dir, max_backups, backup_type):
    """Remove old backup files, keeping only the most recent ones"""
    backup_files = sorted(
        glob.glob(os.path.join(backup_dir, f"{DB_NAME}_backup_*.sql")),
        key=os.path.getmtime
    )
    
    if len(backup_files) > max_backups:
        num_to_delete = len(backup_files) - max_backups
        old_backups = backup_files[:num_to_delete]
        
        for file in old_backups:
            try:
                os.remove(file)
                print(f"Deleted old {backup_type} backup: {os.path.basename(file)}")
                log_event("backup_cleanup", "system", f"Deleted old {backup_type} backup: {file}")
            except Exception as e:
                print(f"Error deleting {file}: {e}")
                log_event("backup_cleanup_error", "system", f"Failed to delete {file}: {e}")

def main():
    """Main backup function"""
    print("🔄 Starting database backup process...")
    
    # Get last backup times
    last_daily_backup = get_last_backup_time(DAILY_BACKUP_DIR)
    last_weekly_backup = get_last_backup_time(WEEKLY_BACKUP_DIR)
    
    now = datetime.now(timezone.utc)
    daily_backup_needed = (now - last_daily_backup) >= timedelta(days=1)
    weekly_backup_needed = (now - last_weekly_backup) >= timedelta(weeks=1)
    
    print(f"📅 Last daily backup: {last_daily_backup.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📅 Last weekly backup: {last_weekly_backup.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 Daily backup needed: {daily_backup_needed}")
    print(f"🔄 Weekly backup needed: {weekly_backup_needed}")
    
    # Create backup filename
    timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{DB_NAME}_backup_{timestamp}.sql"
    
    # Perform daily backup
    if daily_backup_needed:
        daily_backup_path = os.path.join(DAILY_BACKUP_DIR, filename)
        
        if create_backup(daily_backup_path):
            print(f"✅ Daily backup created successfully: {os.path.basename(daily_backup_path)}")
            log_event("backup_success", "system", f"Daily backup created: {daily_backup_path}")
            
            # Cleanup old daily backups
            cleanup_old_backups(DAILY_BACKUP_DIR, MAX_DAILY_BACKUPS, "daily")
        else:
            print("❌ Daily backup failed!")
            log_event("backup_failed", "system", "Daily backup failed")
    
    # Perform weekly backup
    if weekly_backup_needed:
        weekly_backup_path = os.path.join(WEEKLY_BACKUP_DIR, filename)
        print(f"📦 Creating weekly backup: {weekly_backup_path}")
        
        if create_backup(weekly_backup_path):
            print(f"✅ Weekly backup created successfully: {os.path.basename(weekly_backup_path)}")
            log_event("backup_success", "system", f"Weekly backup created: {weekly_backup_path}")
            
            # Cleanup old weekly backups
            cleanup_old_backups(WEEKLY_BACKUP_DIR, MAX_WEEKLY_BACKUPS, "weekly")
        else:
            print("❌ Weekly backup failed!")
            log_event("backup_failed", "system", "Weekly backup failed")
    
    if not daily_backup_needed and not weekly_backup_needed:
        print("ℹ️ No backups needed at this time")
        log_event("backup_skipped", "system", "No backups needed")
    
    print("✅ Backup process completed!")

if __name__ == "__main__":
    main()