# Global HTTPS load balancer in front of the uploads bucket, mirroring
# the existing `scripts/setup_cdn.sh` setup. Off by default; enable in an
# env wrapper by setting enable_cdn = true and cdn_domain.

locals {
  cdn_count = var.enable_cdn ? 1 : 0
}

resource "google_compute_backend_bucket" "uploads" {
  count = local.cdn_count

  project     = var.project_id
  name        = "${local.name_prefix}-uploads-backend"
  description = "CDN-fronted backend for ${google_storage_bucket.uploads.name}"
  bucket_name = google_storage_bucket.uploads.name
  enable_cdn  = true

  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    default_ttl       = 3600
    max_ttl           = 86400
    negative_caching  = true
    serve_while_stale = 86400
  }
}

resource "google_compute_url_map" "cdn" {
  count = local.cdn_count

  project         = var.project_id
  name            = "${local.name_prefix}-cdn"
  default_service = google_compute_backend_bucket.uploads[0].self_link
}

resource "google_compute_managed_ssl_certificate" "cdn" {
  count = local.cdn_count

  project = var.project_id
  name    = "${local.name_prefix}-cdn-cert"

  managed {
    domains = [var.cdn_domain]
  }

  lifecycle {
    create_before_destroy = true
    precondition {
      condition     = var.cdn_domain != null
      error_message = "cdn_domain must be set when enable_cdn = true."
    }
  }
}

resource "google_compute_target_https_proxy" "cdn" {
  count = local.cdn_count

  project          = var.project_id
  name             = "${local.name_prefix}-cdn-proxy"
  url_map          = google_compute_url_map.cdn[0].self_link
  ssl_certificates = [google_compute_managed_ssl_certificate.cdn[0].self_link]
}

resource "google_compute_global_address" "cdn" {
  count = local.cdn_count

  project = var.project_id
  name    = "${local.name_prefix}-cdn-ip"
}

resource "google_compute_global_forwarding_rule" "cdn_https" {
  count = local.cdn_count

  project    = var.project_id
  name       = "${local.name_prefix}-cdn-https"
  ip_address = google_compute_global_address.cdn[0].address
  port_range = "443"
  target     = google_compute_target_https_proxy.cdn[0].self_link
}
