#!/bin/bash
set -e

# Analytics Database Restore Script
# Downloads a production database export from GCS and restores it locally

BUCKET="gyrinx-app-bootstrap-dump"
EXPORT_PREFIX="analytics/gyrinx-"
LOCAL_DIR="./data/analytics"
CONTAINER="postgres-analytics"
PG_USER="postgres"

# Get today's date or use provided date
DATE="${1:-$(date +%Y-%m-%d)}"
DB_NAME="dump_${DATE//-/_}"  # e.g., dump_2025_01_15

echo "=== Analytics Database Restore ==="
echo "Date: $DATE"
echo "Target DB: $DB_NAME"

# Ensure analytics container is running
if ! docker compose ps --status running | grep -q "$CONTAINER"; then
    echo "Starting analytics postgres..."
    docker compose --profile analytics up -d postgres-analytics
    sleep 3
fi

# Create local directory
mkdir -p "$LOCAL_DIR"

# Download the export
REMOTE_FILE="gs://${BUCKET}/${EXPORT_PREFIX}${DATE}.sql.gz"
LOCAL_FILE="${LOCAL_DIR}/gyrinx-${DATE}.sql.gz"

echo "Downloading $REMOTE_FILE..."
if ! gsutil cp "$REMOTE_FILE" "$LOCAL_FILE"; then
    echo "ERROR: Could not download $REMOTE_FILE"
    echo "Available exports:"
    gsutil ls "gs://${BUCKET}/analytics/" | tail -10
    exit 1
fi

# Drop existing database if it exists
echo "Preparing database $DB_NAME..."
docker compose exec -T $CONTAINER psql -U $PG_USER -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" 2>/dev/null || true
docker compose exec -T $CONTAINER psql -U $PG_USER -c "CREATE DATABASE \"$DB_NAME\";"

# Restore
echo "Restoring to $DB_NAME..."
gunzip -c "$LOCAL_FILE" | docker compose exec -T $CONTAINER psql -U $PG_USER -d "$DB_NAME"

# Regenerate structure.sql for reference
echo "Updating analytics/structure.sql..."
docker compose exec -T $CONTAINER pg_dump -U $PG_USER -d "$DB_NAME" \
    --schema-only --no-owner --no-privileges > ./analytics/structure.sql

echo ""
echo "=== Done! ==="
echo "Connect with: psql -h localhost -p 5433 -U postgres -d $DB_NAME"
echo "Or in Python:"
echo "  postgresql://postgres:postgres@localhost:5433/$DB_NAME"
