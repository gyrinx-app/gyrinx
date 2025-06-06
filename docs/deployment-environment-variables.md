# Deployment Environment Variables

## Required Environment Variables for File Uploads

When deploying to production, set these environment variables in your Cloud Run service:

### Google Cloud Storage Configuration

```bash
# Required: Your GCS bucket name for uploaded files
GS_BUCKET_NAME=your-bucket-name

# Optional: Set if using a CDN domain instead of direct GCS
CDN_DOMAIN=cdn.gyrinx.app  # Only if using settings_prod_cdn.py

# Automatically set by Cloud Run, but can be overridden
GOOGLE_CLOUD_PROJECT=your-project-id
```

### Example Cloud Run Deployment

```bash
gcloud run deploy gyrinx \
  --image gcr.io/YOUR_PROJECT/gyrinx:latest \
  --region europe-west2 \
  --set-env-vars "GS_BUCKET_NAME=your-uploads-bucket" \
  --service-account your-service-account@your-project.iam.gserviceaccount.com
```

### Bucket Setup Checklist

1. Create bucket in europe-west2 with uniform access:
   ```bash
   gsutil mb -l europe-west2 -b on gs://your-uploads-bucket
   ```

2. Grant public read access:
   ```bash
   gsutil iam ch allUsers:objectViewer gs://your-uploads-bucket
   ```

3. Grant service account write access:
   ```bash
   gsutil iam ch serviceAccount:YOUR_SA@PROJECT.iam.gserviceaccount.com:objectAdmin gs://your-uploads-bucket
   ```
