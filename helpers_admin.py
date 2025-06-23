import os, subprocess, datetime

def backup_table(db_name, table_name):
    backup_dir = os.path.join('database', 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{db_name}_{table_name}_backup_{timestamp}.sql"
    backup_path = os.path.join(backup_dir, filename)

    user = os.getenv("MYSQL_USER", "tahir")
    pwd = os.getenv("MYSQL_PASSWORD", "tahir")

    command = f'mysqldump -u {user} -p{pwd} {db_name} {table_name} > "{backup_path}"'

    try:
        subprocess.run(command, shell=True, check=True)
        return True, filename
    except subprocess.CalledProcessError as e:
        return False, str(e)
