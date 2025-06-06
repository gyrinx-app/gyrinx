# Setting Up GCS with CDN for Gyrinx

## Option 1: Direct GCS Serving (Current Setup)

### Required GCS Bucket Setup with Uniform Access:
```bash
# Create the bucket with uniform bucket-level access (recommended)
# Using europe-west2 (London) to match your infrastructure
gsutil mb -l europe-west2 -b on gs://YOUR_BUCKET_NAME

# Or enable uniform access on existing bucket
gsutil uniformbucketlevelaccess set on gs://YOUR_BUCKET_NAME

# Grant public read access via IAM (not ACLs)
gsutil iam ch allUsers:objectViewer gs://YOUR_BUCKET_NAME

# Enable CORS for direct browser uploads (if needed)
cat > cors.json << EOF
[
  {
    "origin": ["https://gyrinx.app"],
    "method": ["GET", "HEAD"],
    "maxAgeSeconds": 3600
  }
]
EOF
gsutil cors set cors.json gs://YOUR_BUCKET_NAME
```

### Service Account Permissions:
```bash
# Grant Cloud Run service account upload permissions
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin" \
  --condition="expression=resource.name.startsWith('projects/_/buckets/gyrinx-app-bootstrap-uploads'),title=gyrinx-uploads-bucket"
```

## Option 2: Cloud CDN Setup (Recommended)

### 1. Create Backend Bucket:
```bash
# Create a backend bucket resource
gcloud compute backend-buckets create gyrinx-media-backend \
  --gcs-bucket-name=gyrinx-app-bootstrap-uploads \
  --enable-cdn \
  --cache-mode=CACHE_ALL_STATIC \
  --default-ttl=86400 \
  --max-ttl=31536000
```

### 2. Create URL Map:
```bash
# Create URL map
gcloud compute url-maps create gyrinx-media-cdn \
  --default-backend-bucket=gyrinx-media-backend
```

### 3. Create HTTPS Proxy:
```bash
# Create HTTPS proxy
gcloud compute target-https-proxies create gyrinx-media-https-proxy \
  --url-map=gyrinx-media-cdn \
  --ssl-certificates=YOUR_SSL_CERT
```

### 4. Create Forwarding Rule:
```bash
# Reserve static IP
gcloud compute addresses create gyrinx-media-ip --global

# Create forwarding rule
gcloud compute forwarding-rules create gyrinx-media-https-rule \
  --global \
  --target-https-proxy=gyrinx-media-https-proxy \
  --address=gyrinx-media-ip \
  --ports=443
```

### 5. Update DNS:
Point `cdn.gyrinx.app` to the reserved IP address.

### 6. Update Django Settings:
Use `settings_prod_cdn.py` or set `CDN_DOMAIN=cdn.gyrinx.app` in your environment.

## Option 3: Cloudflare CDN (Easiest)

1. Add your GCS bucket as a Cloudflare origin
2. Create a CNAME record: `cdn.gyrinx.app` → `storage.googleapis.com`
3. Configure page rules:
   - Cache Level: Cache Everything
   - Edge Cache TTL: 1 month
   - Browser Cache TTL: 1 year

## Cache Optimization Tips

### For uploaded images:
- Use immutable cache headers for uploaded files (already configured)
- Consider adding image optimization (WebP conversion, resizing)
- Use consistent URLs (our UUID approach ensures this)

### Security Considerations:
- All uploaded files are publicly readable
- Consider adding a separate bucket for private files if needed
- Monitor bucket access logs for abuse
- Set up bucket lifecycle policies to delete old unused files

## Monitoring

Set up Cloud Monitoring alerts for:
- Bucket size growth
- Request rates
- 4xx/5xx errors
- Bandwidth usage
