# Analytics Database Setup

This document describes how to set up a local analytics environment that queries replicated production data without affecting the production Cloud SQL database.

## Architecture

```
┌─────────────────┐     ┌───────────────────────────────┐     ┌──────────────────┐
│  Cloud SQL      │────▶│  GCS Bucket                   │────▶│ Local Postgres   │
│  (Production)   │     │  gyrinx-app-bootstrap-dump/   │     │ (Analytics)      │
│                 │     │    analytics/                 │     │                  │
└─────────────────┘     └───────────────────────────────┘     └──────────────────┘
      Daily export              Download                        Restore as
      via Scheduler             + Restore                       dump_yyyy_mm_dd
```

## Part 1: GCP Setup

### 1.1 Set lifecycle policy on exports folder

```bash
# Set lifecycle policy to delete exports older than 30 days
cat > /tmp/lifecycle.json << 'EOF'
{
  "rule": [{
    "action": {"type": "Delete"},
    "condition": {"age": 30, "matchesPrefix": ["analytics/"]}
  }]
}
EOF
gsutil lifecycle set /tmp/lifecycle.json gs://gyrinx-app-bootstrap-dump
```

### 1.2 Grant Cloud SQL service account access

```bash
# Get the Cloud SQL instance's service account and store it
GY_SA_DB_EMAIL=$(gcloud sql instances describe gyrinx-app-bootstrap-db \
  --format='value(serviceAccountEmailAddress)')

# Grant it write access to the bucket
gcloud storage buckets add-iam-policy-binding gs://gyrinx-app-bootstrap-dump \
  --member=serviceAccount:$GY_SA_DB_EMAIL \
  --role=roles/storage.objectAdmin
```

### 1.3 Test manual export

```bash
# One-time export to verify the setup works
gcloud sql export sql gyrinx-app-bootstrap-db \
  gs://gyrinx-app-bootstrap-dump/analytics/gyrinx-$(date +%Y-%m-%d).sql.gz \
  --database=app \
  --offload
```

### 1.4 Set up scheduled exports with Cloud Workflows

Create the workflow:

```bash
cat > /tmp/analytics-export-workflow.yaml << 'EOF'
main:
  steps:
    - export_database:
        call: googleapis.sqladmin.v1.instances.export
        args:
          project: windy-ellipse-440618-p9
          instance: gyrinx-app-bootstrap-db
          body:
            exportContext:
              fileType: SQL
              uri: ${"gs://gyrinx-app-bootstrap-dump/analytics/gyrinx-" + text.substring(time.format(sys.now()), 0, 10) + ".sql.gz"}
              databases:
                - app
              offload: true
        result: exportResult
    - return_result:
        return: ${exportResult}
EOF

# Deploy the workflow
gcloud workflows deploy analytics-export \
  --location=europe-west2 \
  --source=/tmp/analytics-export-workflow.yaml
```

Create the scheduler job:

```bash
# Get the default compute service account
PROJECT_ID="windy-ellipse-440618-p9"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
SERVICE_ACCOUNT="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Create scheduler job (daily at 2 AM UK time)
gcloud scheduler jobs create http analytics-export-daily \
  --location=europe-west2 \
  --schedule="0 2 * * *" \
  --time-zone="Europe/London" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/${PROJECT_ID}/locations/europe-west2/workflows/analytics-export/executions" \
  --oauth-service-account-email="$SERVICE_ACCOUNT"
```

Grant the service account permissions:

```bash
# Workflow invoker (to trigger the workflow)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/workflows.invoker"

# Cloud SQL Admin (to call the export API)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/cloudsql.admin"
```

### 1.5 Test the scheduled workflow

```bash
# Manually trigger the workflow to test
gcloud workflows run analytics-export --location=europe-west2

# Check the exports bucket
gsutil ls gs://gyrinx-app-bootstrap-dump/analytics/
```

## Part 2: Local Docker Setup

### 2.1 Add analytics postgres to docker-compose.yml

Add this service definition (uses port 5433 to avoid collision with dev database):

```yaml
  postgres-analytics:
    image: postgres:16.4
    container_name: postgres-analytics
    restart: unless-stopped
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: postgres
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_analytics_data:/var/lib/postgresql/data
    profiles:
      - analytics
```

Add the volume to the volumes section:

```yaml
volumes:
  pgadmin-data:
  postgres_data:
  postgres_analytics_data:
```

### 2.2 Create the restore script

Create `scripts/analytics_restore.sh`:

```bash
#!/bin/bash
set -e

# Configuration
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

echo ""
echo "=== Done! ==="
echo "Connect with: psql -h localhost -p 5433 -U postgres -d $DB_NAME"
echo "Or in Python:"
echo "  postgresql://postgres:postgres@localhost:5433/$DB_NAME"
```

Make it executable:

```bash
chmod +x scripts/analytics_restore.sh
```

## Part 3: Usage

### Start the analytics database

```bash
docker compose --profile analytics up -d postgres-analytics
```

### Restore a specific day's export

```bash
# Today's export
./scripts/analytics_restore.sh

# Specific date
./scripts/analytics_restore.sh 2025-01-15
```

### Connect from Jupyter/Streamlit

```python
import pandas as pd
from sqlalchemy import create_engine

# Connect to analytics database
engine = create_engine("postgresql://postgres:postgres@localhost:5433/dump_2025_01_15")

# Example query
df = pd.read_sql("""
    SELECT date_trunc('day', created_at) as day, count(*)
    FROM core_list
    GROUP BY 1
    ORDER BY 1
""", engine)
```

### List available local databases

```bash
docker compose exec postgres-analytics psql -U postgres -c "\l" | grep dump_
```

### List available exports in GCS

```bash
gsutil ls gs://gyrinx-app-bootstrap-dump/analytics/
```

## Part 4: Maintenance

### Cleanup old local databases

Keep only the last 7 days of local databases:

```bash
docker compose exec postgres-analytics psql -U postgres -t -c "
  SELECT 'DROP DATABASE \"' || datname || '\";'
  FROM pg_database
  WHERE datname LIKE 'dump_%'
  ORDER BY datname DESC
  OFFSET 7
" | docker compose exec -T postgres-analytics psql -U postgres
```

### Check scheduler job status

```bash
gcloud scheduler jobs describe analytics-export-daily --location=europe-west2
```

### View recent workflow executions

```bash
gcloud workflows executions list analytics-export --location=europe-west2 --limit=5
```
