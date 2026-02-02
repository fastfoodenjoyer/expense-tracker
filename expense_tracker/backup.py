"""Database backup service with Cloudflare R2 support."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig

from expense_tracker.bot.config import get_settings

logger = logging.getLogger(__name__)


class BackupService:
    """Service for creating and managing database backups."""

    def __init__(self):
        self.settings = get_settings()
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy initialization of S3 client for Cloudflare R2."""
        if self._s3_client is None and self.settings.r2_enabled:
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.settings.r2_endpoint_url,
                aws_access_key_id=self.settings.r2_access_key_id,
                aws_secret_access_key=self.settings.r2_secret_access_key,
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        return self._s3_client

    def create_backup(self) -> Path:
        """Create a backup of the database using VACUUM INTO."""
        self.settings.ensure_directories()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.settings.backups_dir / f"expenses_{timestamp}.db"

        db_path = self.settings.database_path
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        logger.info(f"Creating backup: {backup_path}")

        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(f"VACUUM INTO '{backup_path}'")
        finally:
            conn.close()

        logger.info(f"Backup created successfully: {backup_path}")
        return backup_path

    def upload_to_r2(self, backup_path: Path) -> str | None:
        """Upload backup file to Cloudflare R2."""
        if not self.settings.r2_enabled:
            logger.warning("R2 is not configured, skipping upload")
            return None

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        key = f"backups/{backup_path.name}"

        try:
            logger.info(f"Uploading backup to R2: {key}")
            self.s3_client.upload_file(
                str(backup_path),
                self.settings.r2_bucket_name,
                key,
            )
            logger.info(f"Backup uploaded successfully to R2: {key}")
            return key
        except Exception as e:
            logger.error(f"Failed to upload backup to R2: {e}")
            raise

    def create_and_upload_backup(self) -> tuple[Path, str | None]:
        """Create backup and upload to R2 if configured."""
        backup_path = self.create_backup()
        r2_key = None

        if self.settings.r2_enabled:
            try:
                r2_key = self.upload_to_r2(backup_path)
            except Exception as e:
                logger.error(f"R2 upload failed, but local backup exists: {e}")

        return backup_path, r2_key

    def list_backups(self) -> list[Path]:
        """List all available local backups sorted by date (newest first)."""
        if not self.settings.backups_dir.exists():
            return []

        backups = list(self.settings.backups_dir.glob("expenses_*.db"))
        return sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)

    def list_r2_backups(self) -> list[dict]:
        """List all backups in R2 bucket."""
        if not self.settings.r2_enabled:
            return []

        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.settings.r2_bucket_name,
                Prefix="backups/",
            )
            objects = response.get("Contents", [])
            return sorted(objects, key=lambda x: x["LastModified"], reverse=True)
        except Exception as e:
            logger.error(f"Failed to list R2 backups: {e}")
            return []

    def cleanup_old_backups(self, keep_count: int = 7) -> int:
        """Remove old local backups, keeping only the most recent ones."""
        backups = self.list_backups()
        removed = 0

        for backup in backups[keep_count:]:
            try:
                backup.unlink()
                logger.info(f"Removed old backup: {backup}")
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove backup {backup}: {e}")

        return removed

    def cleanup_old_r2_backups(self, keep_count: int = 7) -> int:
        """Remove old R2 backups, keeping only the most recent ones."""
        if not self.settings.r2_enabled:
            return 0

        backups = self.list_r2_backups()
        removed = 0

        for backup in backups[keep_count:]:
            try:
                self.s3_client.delete_object(
                    Bucket=self.settings.r2_bucket_name,
                    Key=backup["Key"],
                )
                logger.info(f"Removed old R2 backup: {backup['Key']}")
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove R2 backup {backup['Key']}: {e}")

        return removed

    def download_from_r2(self, r2_key: str, destination: Path) -> Path:
        """Download a specific backup from R2."""
        if not self.settings.r2_enabled:
            raise RuntimeError("R2 is not configured")

        try:
            logger.info(f"Downloading backup from R2: {r2_key} -> {destination}")
            self.s3_client.download_file(
                self.settings.r2_bucket_name,
                r2_key,
                str(destination),
            )
            logger.info(f"Backup downloaded successfully: {destination}")
            return destination
        except Exception as e:
            logger.error(f"Failed to download backup from R2: {e}")
            raise

    def restore_latest_from_r2(self) -> bool:
        """Restore database from the latest R2 backup.

        Returns:
            True if restoration was successful, False otherwise.
        """
        if not self.settings.r2_enabled:
            logger.warning("R2 is not configured, cannot restore from R2")
            return False

        r2_backups = self.list_r2_backups()
        if not r2_backups:
            logger.warning("No backups found in R2")
            return False

        latest_backup = r2_backups[0]
        r2_key = latest_backup["Key"]

        logger.info(f"Found latest R2 backup: {r2_key} (modified: {latest_backup['LastModified']})")

        self.settings.ensure_directories()

        temp_backup = self.settings.backups_dir / "restore_temp.db"
        try:
            self.download_from_r2(r2_key, temp_backup)

            # Verify the downloaded backup is valid SQLite database
            try:
                conn = sqlite3.connect(str(temp_backup))
                conn.execute("PRAGMA integrity_check")
                conn.close()
                logger.info("Downloaded backup integrity check passed")
            except Exception as e:
                logger.error(f"Downloaded backup is corrupted: {e}")
                temp_backup.unlink(missing_ok=True)
                return False

            db_path = self.settings.database_path
            if db_path.exists():
                backup_old = self.settings.backups_dir / f"before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                db_path.rename(backup_old)
                logger.info(f"Existing database backed up to: {backup_old}")

            temp_backup.rename(db_path)
            logger.info(f"Database restored successfully from R2: {r2_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore database from R2: {e}")
            temp_backup.unlink(missing_ok=True)
            return False

    def check_database_exists(self) -> bool:
        """Check if database exists and has tables."""
        db_path = self.settings.database_path
        if not db_path.exists():
            return False

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            conn.close()
            return len(tables) > 0
        except Exception as e:
            logger.warning(f"Failed to check database: {e}")
            return False
