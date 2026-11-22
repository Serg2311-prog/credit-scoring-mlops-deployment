variable "name_prefix" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "log_retention_days" {
  description = "Cloud Logging retention period in days (converted to duration string)."
  type        = number
  default     = 14

  validation {
    condition     = var.log_retention_days >= 1 && var.log_retention_days <= 365
    error_message = "log_retention_days must be between 1 and 365."
  }
}

variable "environment" {
  description = "Environment label value (staging|production)."
  type        = string
}
