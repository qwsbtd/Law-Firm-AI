#!/bin/bash
# Daily backup of Law Firm AI data to DigitalOcean Spaces (S3-compatible)
# Prerequisites: apt install s3cmd, then run: s3cmd --configure
# Add to crontab: 0 2 * * * /opt/law-firm-ai/scripts/backup.sh

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/lawfirm-backup-${TIMESTAMP}"
ARCHIVE="/tmp/lawfirm-${TIMESTAMP}.tar.gz"
BUCKET="s3://YOUR_SPACES_BUCKET/backups"
DATA_DIR="/var/lib/docker/volumes/law-firm-ai_law-firm-data/_data"

echo "[$(date)] Starting backup..."

mkdir -p "${BACKUP_DIR}"

# Copy SQLite database and ChromaDB vectors
cp "${DATA_DIR}/law_firm.db" "${BACKUP_DIR}/" 2>/dev/null || echo "Warning: law_firm.db not found"
cp -r "${DATA_DIR}/chroma" "${BACKUP_DIR}/" 2>/dev/null || echo "Warning: chroma dir not found"
cp -r "${DATA_DIR}/uploads" "${BACKUP_DIR}/" 2>/dev/null || echo "Warning: uploads dir not found"

# Compress
tar -czf "${ARCHIVE}" -C /tmp "lawfirm-backup-${TIMESTAMP}"

# Upload to Spaces
s3cmd put "${ARCHIVE}" "${BUCKET}/"

echo "[$(date)] Uploaded ${ARCHIVE} to ${BUCKET}"

# Delete local backup files
rm -rf "${BACKUP_DIR}" "${ARCHIVE}"

# Remove backups older than 30 days from Spaces
s3cmd ls "${BUCKET}/" | awk '{print $4}' | sort | head -n -30 | while read -r old; do
    s3cmd del "$old"
    echo "[$(date)] Removed old backup: $old"
done

echo "[$(date)] Backup complete."
