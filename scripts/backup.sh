#!/usr/bin/env bash
# NetScan backup script
# Add to cron: 0 3 * * * /home/matheau/code/port_scan/scripts/backup.sh

set -euo pipefail

BACKUP_DIR="/home/matheau/code/port_scan/backups"
DATE=$(date +%Y%m%d)
DOTENV="/home/matheau/code/port_scan/.env"

mkdir -p "$BACKUP_DIR"

# Parse DB credentials from .env
DB_URL=$(grep -E '^DATABASE_URL=' "$DOTENV" | cut -d= -f2-)
# Extract user:password@host:port/dbname from mysql+pymysql://...
CREDENTIALS=$(echo "$DB_URL" | sed 's|mysql+pymysql://||')
DB_USER=$(echo "$CREDENTIALS" | cut -d: -f1)
DB_PASS=$(echo "$CREDENTIALS" | cut -d: -f2 | cut -d@ -f1)
DB_HOST=$(echo "$CREDENTIALS" | cut -d@ -f2 | cut -d/ -f1 | cut -d: -f1)
DB_NAME=$(echo "$CREDENTIALS" | cut -d/ -f2)

# Database backup
echo "Backing up database $DB_NAME..."
mysqldump -u "$DB_USER" -p"$DB_PASS" -h "$DB_HOST" "$DB_NAME" \
    > "$BACKUP_DIR/db_${DATE}.sql"
echo "Database backup: $BACKUP_DIR/db_${DATE}.sql"

# Screenshots backup
SCREENSHOTS_DIR="/home/matheau/code/port_scan/screenshots"
if [ -d "$SCREENSHOTS_DIR" ] && [ "$(ls -A "$SCREENSHOTS_DIR")" ]; then
    echo "Backing up screenshots..."
    tar -czf "$BACKUP_DIR/screenshots_${DATE}.tar.gz" -C "$(dirname "$SCREENSHOTS_DIR")" "$(basename "$SCREENSHOTS_DIR")"
    echo "Screenshots backup: $BACKUP_DIR/screenshots_${DATE}.tar.gz"
fi

# Prune backups older than 30 days
find "$BACKUP_DIR" -name "db_*.sql" -mtime +30 -delete
find "$BACKUP_DIR" -name "screenshots_*.tar.gz" -mtime +30 -delete

echo "Backup complete."
