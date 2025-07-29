#!/usr/bin/env python3
"""
Madrasa App Maintenance Script
This script performs periodic maintenance tasks like auto deletion and backups.
"""

import asyncio, os, sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helpers import delete_users, log_event
from database.backup_db import main as backup_main

async def run_maintenance():
    """Run all maintenance tasks"""
    print(f"🔧 Starting maintenance at {datetime.now()}")
    
    try:
        # Run auto deletion
        print("🗑️  Running auto deletion...")
        await delete_users()
        print("✅ Auto deletion completed")
        
        # Run backup
        print("💾 Running database backup...")
        backup_main()
        print("✅ Database backup completed")
        
        # Log the maintenance
        log_event("maintenance_completed", "system", "Periodic maintenance completed successfully")
        print("✅ Maintenance completed successfully")
        
    except Exception as e:
        error_msg = f"Maintenance failed: {str(e)}"
        print(f"❌ {error_msg}")
        log_event("maintenance_failed", "system", error_msg)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_maintenance()) 