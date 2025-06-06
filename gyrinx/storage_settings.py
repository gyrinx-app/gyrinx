"""
Google Cloud Storage configuration for media files.

This module contains the common GCS configuration used by both
development (when USE_GCS_IN_DEV=True) and production environments.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def configure_gcs_storage(storages_dict):
    """
    Configure Google Cloud Storage settings for media files.

    Args:
        storages_dict: The STORAGES dictionary to update

    Returns:
        dict: Configuration values including MEDIA_URL
    """
    # Use CDN domain if available, otherwise fall back to direct GCS access
    cdn_domain = os.environ.get("CDN_DOMAIN", None)

    config = {
        "DEFAULT_FILE_STORAGE": "storages.backends.gcloud.GoogleCloudStorage",
        "GS_BUCKET_NAME": os.environ.get(
            "GS_BUCKET_NAME", "gyrinx-app-bootstrap-uploads"
        ),
        "GS_PROJECT_ID": os.environ.get(
            "GOOGLE_CLOUD_PROJECT", "windy-ellipse-440618-p9"
        ),
        "GS_DEFAULT_ACL": None,  # ACLs are disabled with uniform access
        "GS_QUERYSTRING_AUTH": False,
        "GS_OBJECT_PARAMETERS": {
            "CacheControl": "public, max-age=2592000",  # 30 days for uploaded images
        },
        "CDN_DOMAIN": cdn_domain,
    }

    # Media URL configuration
    if cdn_domain:
        config["MEDIA_URL"] = f"https://{cdn_domain}/"
    else:
        # Fall back to direct GCS access
        config["MEDIA_URL"] = (
            f"https://storage.googleapis.com/{config['GS_BUCKET_NAME']}/"
        )

    # Update STORAGES to use GCS as default
    storages_dict["default"] = {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
        "OPTIONS": {
            "bucket_name": config["GS_BUCKET_NAME"],
            "project_id": config["GS_PROJECT_ID"],
            "default_acl": config["GS_DEFAULT_ACL"],
            "querystring_auth": config["GS_QUERYSTRING_AUTH"],
            "object_parameters": config["GS_OBJECT_PARAMETERS"],
        },
    }

    return config
