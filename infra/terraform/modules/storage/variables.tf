variable "name_prefix" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "bucket_name" {
  description = "Globally unique Object Storage bucket name."
  type        = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "enable_versioning" {
  type    = bool
  default = true
}

variable "enable_kms_encryption" {
  description = "Create KMS key and enable SSE-KMS on the bucket."
  type        = bool
  default     = true
}

variable "lifecycle_noncurrent_days" {
  description = "Expire noncurrent versions after N days (when versioning enabled)."
  type        = number
  default     = 90
}

variable "lifecycle_abort_multipart_days" {
  type    = number
  default = 7
}

variable "max_size_bytes" {
  description = "Optional soft max bucket size in bytes (0 = unlimited)."
  type        = number
  default     = 0
}
