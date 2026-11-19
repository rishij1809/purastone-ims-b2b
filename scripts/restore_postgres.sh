#!/usr/bin/env bash
# ==============================================================================
# Pura Stone Skincare ERP - Restore Encrypted PostgreSQL Backup
# Usage: ./restore_postgres.sh /backups/purastone_db_YYYYMMDD_HHMMSS.dump.enc
# ==============================================================================
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path_to_encrypted_dump.enc>"
    exit 1
fi

ENC_FILE="$1"
if [ ! -f "${ENC_FILE}" ]; then
    echo "Error: Encrypted backup file does not exist: ${ENC_FILE}"
    exit 1
fi

DB_NAME="${DB_NAME:-purastone_db}"
DB_USER="${DB_USER:-purastone_admin}"
DB_HOST="${DB_HOST:-db-primary}"
DB_PORT="${DB_PORT:-5432}"
ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-PurastoneAES256BackupSecretKey2026!}"

DEC_FILE="${ENC_FILE%.enc}"

# Verify checksum if .sha256 file exists alongside
SHA_FILE="${ENC_FILE%.dump.enc}.sha256"
if [ -f "${SHA_FILE}" ]; then
    echo "Verifying SHA-256 checksum..."
    sha256sum -c "${SHA_FILE}"
fi

echo "Decrypting ${ENC_FILE} using OpenSSL AES-256-CBC..."
openssl enc -d -aes-256-cbc \
    -pbkdf2 \
    -iter 100000 \
    -in "${ENC_FILE}" \
    -out "${DEC_FILE}" \
    -pass pass:"${ENCRYPTION_KEY}"

echo "Restoring database ${DB_NAME} on ${DB_HOST}:${DB_PORT}..."
PGPASSWORD="${DB_PASSWORD:-PurastoneP0stgresSecure2026!}" pg_restore \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    -v "${DEC_FILE}"

# Cleanup decrypted temp file
rm -f "${DEC_FILE}"

echo "Database restoration completed successfully."
