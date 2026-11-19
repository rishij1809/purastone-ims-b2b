#!/usr/bin/env bash
# ==============================================================================
# Pura Stone Skincare ERP - Daily Automated AES-256 Encrypted PostgreSQL Backup
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DB_NAME="${DB_NAME:-purastone_db}"
DB_USER="${DB_USER:-purastone_admin}"
DB_HOST="${DB_HOST:-db-primary}"
DB_PORT="${DB_PORT:-5432}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-PurastoneAES256BackupSecretKey2026!}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

mkdir -p "${BACKUP_DIR}"

RAW_DUMP="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
ENC_DUMP="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump.enc"
SHA_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sha256"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting PostgreSQL dump for database: ${DB_NAME}..."

# Export compressed binary custom dump
PGPASSWORD="${DB_PASSWORD:-PurastoneP0stgresSecure2026!}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    -F c \
    -b \
    -v \
    -f "${RAW_DUMP}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Encrypting backup with OpenSSL AES-256-CBC (PBKDF2)..."
openssl enc -aes-256-cbc \
    -salt \
    -pbkdf2 \
    -iter 100000 \
    -in "${RAW_DUMP}" \
    -out "${ENC_DUMP}" \
    -pass pass:"${ENCRYPTION_KEY}"

# Generate SHA-256 checksum of encrypted file for integrity verification
sha256sum "${ENC_DUMP}" > "${SHA_FILE}"

# Remove unencrypted temporary dump
rm -f "${RAW_DUMP}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup complete: ${ENC_DUMP}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Integrity Checksum: $(cat ${SHA_FILE})"

# Apply retention policy: remove backups older than RETENTION_DAYS
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -type f -name "${DB_NAME}_*.dump.enc" -mtime +"${RETENTION_DAYS}" -exec rm -f {} \;
find "${BACKUP_DIR}" -type f -name "${DB_NAME}_*.sha256" -mtime +"${RETENTION_DAYS}" -exec rm -f {} \;

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Automated backup and rotation completed successfully."
