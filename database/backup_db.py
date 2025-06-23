import os
import datetime
import subprocess
import glob

# ======= Configuration ========
DB_NAME = "madrasadb"
DB_USER = "tahir"
DB_PASSWORD = "tahir"
MAX_BACKUPS = 20

# ======= Paths ========
BASE_DIR = os.path.dirname(__file__)
BACKUP_DIR = os.path.join(BASE_DIR, "database", "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

# ======= Create backup filename ========
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
filename = f"{DB_NAME}_backup_{timestamp}.sql"
backup_path = os.path.join(BACKUP_DIR, filename)

# ======= Run mysqldump ========
dump_command = f"mysqldump -u {DB_USER} -p{DB_PASSWORD} {DB_NAME} > \"{backup_path}\""

try:
    subprocess.run(dump_command, shell=True, check=True)
    print(f"✅ Backup created: {backup_path}")
except subprocess.CalledProcessError as e:
    print(f"❌ Backup failed: {e}")
    exit(1)

# ======= Cleanup Old Backups ========
backups = sorted(glob.glob(os.path.join(BACKUP_DIR, f"{DB_NAME}_backup_*.sql")))

if len(backups) > MAX_BACKUPS:
    num_to_delete = len(backups) - MAX_BACKUPS
    old_backups = backups[:num_to_delete]
    for file in old_backups:
        try:
            os.remove(file)
            print(f"🗑 Deleted old backup: {file}")
        except Exception as e:
            print(f"⚠️ Error deleting {file}: {e}")
