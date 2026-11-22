resource "yandex_kms_symmetric_key" "artifacts" {
  count = var.enable_kms_encryption ? 1 : 0

  folder_id         = var.folder_id
  name              = "${var.name_prefix}-artifacts-kms"
  description       = "SSE-KMS key for ML artifacts bucket"
  default_algorithm = "AES_256"
  rotation_period   = "8760h"
  labels            = var.labels
}

resource "yandex_storage_bucket" "artifacts" {
  bucket    = var.bucket_name
  folder_id = var.folder_id
  # Default bucket ACL is private. Avoid deprecated `acl` argument
  # (provider warns to use yandex_storage_bucket_grant instead).

  # Explicit deny of anonymous access.
  anonymous_access_flags {
    read        = false
    list        = false
    config_read = false
  }

  versioning {
    enabled = var.enable_versioning
  }

  dynamic "server_side_encryption_configuration" {
    for_each = var.enable_kms_encryption ? [1] : []
    content {
      rule {
        apply_server_side_encryption_by_default {
          kms_master_key_id = yandex_kms_symmetric_key.artifacts[0].id
          sse_algorithm     = "aws:kms"
        }
      }
    }
  }

  lifecycle_rule {
    id                                     = "abort-incomplete-multipart"
    enabled                                = true
    abort_incomplete_multipart_upload_days = var.lifecycle_abort_multipart_days
  }

  dynamic "lifecycle_rule" {
    for_each = var.enable_versioning ? [1] : []
    content {
      id      = "expire-noncurrent-versions"
      enabled = true
      noncurrent_version_expiration {
        days = var.lifecycle_noncurrent_days
      }
    }
  }

  max_size = var.max_size_bytes > 0 ? var.max_size_bytes : null

  tags = var.labels
}
