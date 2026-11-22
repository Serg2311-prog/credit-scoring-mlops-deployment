variable "cloud_id" {
  type = string
}

variable "folder_id" {
  description = "Production folder ID (prefer a folder separate from staging)."
  type        = string
}

variable "zone" {
  type    = string
  default = "ru-central1-a"
}

variable "name_prefix" {
  type    = string
  default = "cs-prod"
}

variable "artifacts_bucket_name" {
  type = string
}

variable "k8s_api_allowed_cidrs" {
  type    = list(string)
  default = []
}

variable "kubernetes_version" {
  type    = string
  default = "1.30"
}

variable "node_count" {
  type    = number
  default = 2
}

variable "node_cores" {
  type    = number
  default = 2
}

variable "node_memory_gb" {
  type    = number
  default = 8
}

variable "node_preemptible" {
  description = "Production default is non-preemptible for stability."
  type        = bool
  default     = false
}

variable "public_master_ip" {
  type    = bool
  default = false
}

variable "enable_load_balancer_admin" {
  description = "Enable when introducing cloud Load Balancer / Ingress."
  type        = bool
  default     = false
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "extra_labels" {
  type    = map(string)
  default = {}
}
