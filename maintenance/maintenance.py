#!/usr/bin/env python3
"""Enhanced Madrasa App Maintenance Script
This script performs periodic maintenance tasks with advanced monitoring and error handling."""

import asyncio, os, sys
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from utils.helpers.helpers import delete_users
from utils.helpers.logger import log
from maintenance.backup_db import main as backup_main

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup enhanced logging
def setup_maintenance_logging():
    """Setup enhanced logging for maintenance tasks"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create maintenance-specific logger
    maintenance_logger = logging.getLogger("maintenance")
    maintenance_logger.setLevel(logging.INFO)
    
    # File handler
    log_file = log_dir / f"maintenance_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    maintenance_logger.addHandler(file_handler)
    
    return maintenance_logger

async def run_maintenance():
    """Run all maintenance tasks with enhanced monitoring"""
    logger = setup_maintenance_logging()
    start_time = datetime.now()
    
    logger.info(f"🔧 Starting enhanced maintenance at {start_time}")
    print(f"🔧 Starting enhanced maintenance at {start_time}")
    
    maintenance_results = {
        "start_time": start_time.isoformat(),
        "tasks": {},
        "overall_status": "success",
        "errors": []
    }
    
    try:
        # Task 1: Auto deletion
        logger.info("🗑️  Starting auto deletion task...")
        print("🗑️  Running auto deletion...")
        
        task_start = datetime.now()
        try:
            await delete_users()
            task_duration = (datetime.now() - task_start).total_seconds()
            maintenance_results["tasks"]["auto_deletion"] = {
                "status": "success",
                "duration": task_duration,
                "message": "Auto deletion completed successfully"
            }
            logger.info(f"✅ Auto deletion completed in {task_duration:.2f}s")
            print("✅ Auto deletion completed")
            
        except Exception as e:
            task_duration = (datetime.now() - task_start).total_seconds()
            error_msg = f"Auto deletion failed: {type(e).__name__}"
            maintenance_results["tasks"]["auto_deletion"] = {
                "status": "failed",
                "duration": task_duration,
                "error": type(e).__name__
            }
            maintenance_results["errors"].append(error_msg)
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            log.error(action="maintenance_auto_deletion_failed", trace_info="system", message=error_msg, secure=False)
        
        # Task 2: Database backup
        logger.info("💾 Starting database backup task...")
        print("💾 Running database backup...")
        
        task_start = datetime.now()
        try:
            # Run backup_main in executor since it's synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, backup_main)
            task_duration = (datetime.now() - task_start).total_seconds()
            maintenance_results["tasks"]["database_backup"] = {
                "status": "success",
                "duration": task_duration,
                "message": "Database backup completed successfully"
            }
            logger.info(f"✅ Database backup completed in {task_duration:.2f}s")
            print("✅ Database backup completed")
            
        except Exception as e:
            task_duration = (datetime.now() - task_start).total_seconds()
            error_msg = f"Database backup failed: {type(e).__name__}"
            maintenance_results["tasks"]["database_backup"] = {
                "status": "failed",
                "duration": task_duration,
                "error": type(e).__name__
            }
            maintenance_results["errors"].append(error_msg)
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            log.error(action="maintenance_backup_failed", trace_info="system", message=error_msg, secure=False)
        
        # Task 3: Log cleanup (new)
        logger.info("🧹 Starting log cleanup task...")
        print("🧹 Running log cleanup...")
        
        task_start = datetime.now()
        try:
            await cleanup_old_logs()
            task_duration = (datetime.now() - task_start).total_seconds()
            maintenance_results["tasks"]["log_cleanup"] = {
                "status": "success",
                "duration": task_duration,
                "message": "Log cleanup completed successfully"
            }
            logger.info(f"✅ Log cleanup completed in {task_duration:.2f}s")
            print("✅ Log cleanup completed")
            
        except Exception as e:
            task_duration = (datetime.now() - task_start).total_seconds()
            error_msg = f"Log cleanup failed: {type(e).__name__}"
            maintenance_results["tasks"]["log_cleanup"] = {
                "status": "failed",
                "duration": task_duration,
                "error": type(e).__name__
            }
            maintenance_results["errors"].append(error_msg)
            logger.error(error_msg)
            print(f"❌ {error_msg}")
            log.error(action="maintenance_log_cleanup_failed", trace_info="system", message=error_msg, secure=False)
        
        # Overall status
        total_duration = (datetime.now() - start_time).total_seconds()
        maintenance_results["end_time"] = datetime.now().isoformat()
        maintenance_results["total_duration"] = total_duration
        
        if maintenance_results["errors"]:
            maintenance_results["overall_status"] = "partial_failure"
            logger.warning(f"⚠️ Maintenance completed with {len(maintenance_results['errors'])} errors")
            print(f"⚠️ Maintenance completed with {len(maintenance_results['errors'])} errors")
        else:
            maintenance_results["overall_status"] = "success"
            logger.info("✅ Maintenance completed successfully")
            print("✅ Maintenance completed successfully")
        
        # Log the maintenance results
        log.info(action="maintenance_completed", trace_info="system", message=f"Maintenance completed with status: {maintenance_results['overall_status']}", metadata=maintenance_results, secure=False)
        
        # Save maintenance report
        await save_maintenance_report(maintenance_results)
        
    except Exception as e:
        error_msg = f"Maintenance script failed: {type(e).__name__}"
        logger.critical(error_msg)
        print(f"❌ {error_msg}")
        log.critical(action="maintenance_script_failed", trace_info="system", message=error_msg, secure=False)
        sys.exit(1)

async def cleanup_old_logs():
    """Clean up old log files"""
    try:
        log_dir = Path("logs")
        if not log_dir.exists():
            return
        
        # Keep logs for 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        deleted_count = 0
        
        for log_file in log_dir.glob("*.log"):
            try:
                # Check file modification time
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff_date:
                    log_file.unlink()
                    deleted_count += 1
            except Exception as e:
                logger = logging.getLogger("maintenance")
                logger.warning(f"Error deleting log file {log_file.name}: {type(e).__name__}")
        
        return deleted_count
        
    except Exception as e:
        raise Exception(f"Log cleanup failed: {type(e).__name__}")

async def save_maintenance_report(results):
    """Save maintenance report to file"""
    try:
        reports_dir = Path("logs/maintenance_reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = reports_dir / f"maintenance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Use mode 0o600 for security
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)
        report_file.chmod(0o600)
            
    except Exception as e:
        logger = logging.getLogger("maintenance")
        logger.error(f"Failed to save maintenance report: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(run_maintenance()) 