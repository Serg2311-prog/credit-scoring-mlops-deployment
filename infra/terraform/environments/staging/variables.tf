variable "cloud_id" {
  description = "Yandex Cloud ID."
  type        = string
}

variable "folder_id" {
  description = "Staging folder ID (prefer dedicated folder)."
  type        = string
}

variable "zone" {
  description = "Default zone for provider and zonal master."
  type        = string
  default     = "ru-central1-a"
}

variable "name_prefix" {
  type    = string
  default = "cs-stg"
}

variable "artifacts_bucket_name" {
  description = "Globally unique private bucket for ML artifacts."
  type        = string
}

variable "k8s_api_allowed_cidrs" {
  description = "Admin CIDRs for Kubernetes API (empty = no API ingress from internet)."
  type        = list(string)
  default     = []
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "node_count" {
  type    = number
  default = 1
}

variable "node_cores" {
  type    = number
  default = 2
}

variable "node_memory_gb" {
  type    = number
  default = 4
}

variable "node_preemptible" {
  type    = bool
  default = true
}

variable "public_master_ip" {
  type    = bool
  default = false
}

variable "enable_load_balancer_admin" {
  type    = bool
  default = false
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "extra_labels" {
  type    = map(string)
  default = {}
}
