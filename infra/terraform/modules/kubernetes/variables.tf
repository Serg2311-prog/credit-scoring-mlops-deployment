variable "name_prefix" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "network_id" {
  type = string
}

variable "subnet_id" {
  description = "Primary subnet for zonal master and default node group."
  type        = string
}

variable "master_zone" {
  description = "Availability zone for zonal Kubernetes master."
  type        = string
}

variable "master_security_group_ids" {
  type = list(string)
}

variable "node_security_group_ids" {
  type = list(string)
}

variable "cluster_service_account_id" {
  type = string
}

variable "node_service_account_id" {
  type = string
}

variable "iam_dependency_ids" {
  description = "IAM binding IDs that must exist before creating the cluster."
  type        = list(string)
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "kubernetes_version" {
  description = "Kubernetes version (must be supported by Yandex Managed Kubernetes)."
  type        = string
  default     = "1.30"
}

variable "release_channel" {
  type    = string
  default = "REGULAR"

  validation {
    condition     = contains(["RAPID", "REGULAR", "STABLE"], var.release_channel)
    error_message = "release_channel must be RAPID, REGULAR, or STABLE."
  }
}

variable "public_ip" {
  description = "Expose public IP on Kubernetes master. Prefer false + private access when possible."
  type        = bool
  default     = false
}

variable "network_policy_provider" {
  type    = string
  default = "CALICO"
}

variable "log_group_id" {
  description = "Cloud Logging group for master logging (optional empty to disable)."
  type        = string
  default     = ""
}

variable "enable_master_logging" {
  type    = bool
  default = true
}

variable "node_group_name" {
  type    = string
  default = "cpu-workers"
}

variable "node_count" {
  type    = number
  default = 1

  validation {
    condition     = var.node_count >= 1 && var.node_count <= 10
    error_message = "node_count must be between 1 and 10 for this module."
  }
}

variable "node_platform_id" {
  description = "Compute platform. standard-v3 is widely available; verify before apply."
  type        = string
  default     = "standard-v3"
}

variable "node_cores" {
  type    = number
  default = 2
}

variable "node_memory_gb" {
  type    = number
  default = 4
}

variable "node_core_fraction" {
  description = "vCPU fraction percent (20/50/100). Use 100 for latency-sensitive serving."
  type        = number
  default     = 100
}

variable "node_disk_type" {
  type    = string
  default = "network-ssd"
}

variable "node_disk_size_gb" {
  type    = number
  default = 64
}

variable "node_preemptible" {
  description = "Use preemptible nodes (cheaper, less reliable). Staging only recommended."
  type        = bool
  default     = false
}
