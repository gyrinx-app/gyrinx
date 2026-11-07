"""Shared Google Cloud Storage settings for production and optional development use."""

import os

from dotenv import load_dotenv

load_dotenv()


def configure_gcs_storage(storages_dict):
    """Set the default backend in storages_dict and return media configuration.

    Use CDN_DOMAIN for public media URLs when configured, otherwise the
    bucket's storage.googleapis.com URL.
    """
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

    if cdn_domain:
        config["MEDIA_URL"] = f"https://{cdn_domain}/"
    else:
        config["MEDIA_URL"] = (
            f"https://storage.googleapis.com/{config['GS_BUCKET_NAME']}/"
        )

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
