#!/bin/bash
# Script to set up Google Cloud CDN for Gyrinx uploads

set -e

PROJECT_ID="windy-ellipse-440618-p9"
BUCKET_NAME="gyrinx-app-bootstrap-uploads"
CDN_DOMAIN="cdn.gyrinx.app"

echo "Setting up Google Cloud CDN for Gyrinx uploads..."
echo "Project: $PROJECT_ID"
echo "Bucket: $BUCKET_NAME"
echo "CDN Domain: $CDN_DOMAIN"
echo ""

# Check if gcloud is configured correctly
echo "Checking gcloud configuration..."
CURRENT_PROJECT=$(gcloud config get-value project)
if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
    echo "Switching to project $PROJECT_ID..."
    gcloud config set project $PROJECT_ID
fi

# 1. Create backend bucket
echo "Creating backend bucket..."
if gcloud compute backend-buckets describe gyrinx-uploads-backend --quiet 2>/dev/null; then
    echo "Backend bucket already exists, skipping..."
else
    gcloud compute backend-buckets create gyrinx-uploads-backend \
        --gcs-bucket-name=$BUCKET_NAME \
        --enable-cdn \
        --cache-mode=CACHE_ALL_STATIC \
        --default-ttl=3600 \
        --max-ttl=86400 \
        --negative-caching
fi

# 2. Create URL map
echo "Creating URL map..."
if gcloud compute url-maps describe gyrinx-cdn --quiet 2>/dev/null; then
    echo "URL map already exists, skipping..."
else
    gcloud compute url-maps create gyrinx-cdn \
        --default-backend-bucket=gyrinx-uploads-backend
fi

# 3. Create SSL certificate
echo "Creating SSL certificate for $CDN_DOMAIN..."
if gcloud compute ssl-certificates describe gyrinx-cdn-cert --quiet 2>/dev/null; then
    echo "SSL certificate already exists, skipping..."
else
    gcloud compute ssl-certificates create gyrinx-cdn-cert \
        --domains=$CDN_DOMAIN \
        --global
fi

# 4. Create HTTPS proxy
echo "Creating HTTPS proxy..."
if gcloud compute target-https-proxies describe gyrinx-cdn-proxy --quiet 2>/dev/null; then
    echo "HTTPS proxy already exists, skipping..."
else
    gcloud compute target-https-proxies create gyrinx-cdn-proxy \
        --url-map=gyrinx-cdn \
        --ssl-certificates=gyrinx-cdn-cert \
        --global
fi

# 5. Create forwarding rule
echo "Creating forwarding rule..."
if gcloud compute forwarding-rules describe gyrinx-cdn-https --global --quiet 2>/dev/null; then
    echo "Forwarding rule already exists, skipping..."
else
    gcloud compute forwarding-rules create gyrinx-cdn-https \
        --target-https-proxy=gyrinx-cdn-proxy \
        --ports=443 \
        --global
fi

# 6. Get IP address
echo ""
echo "Getting CDN IP address..."
CDN_IP=$(gcloud compute forwarding-rules describe gyrinx-cdn-https --global --format="value(IPAddress)")
echo "CDN IP Address: $CDN_IP"

echo ""
echo "Setup complete! Next steps:"
echo "1. Create an A record for $CDN_DOMAIN pointing to $CDN_IP"
echo "2. Wait for DNS propagation (usually 5-10 minutes)"
echo "3. Wait for SSL certificate provisioning (can take up to 20 minutes)"
echo "4. Set the CDN_DOMAIN environment variable in your deployment:"
echo "   CDN_DOMAIN=$CDN_DOMAIN"
echo "5. Deploy using settings_prod_cdn.py instead of settings_prod.py"
echo ""
echo "To check SSL certificate status:"
echo "gcloud compute ssl-certificates describe gyrinx-cdn-cert"
echo ""
echo "To check CDN status:"
echo "gcloud compute backend-buckets describe gyrinx-uploads-backend"
