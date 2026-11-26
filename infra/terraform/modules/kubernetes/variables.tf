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

variable "security_group_dependency_ids" {
  description = <<-EOT
    Security group rule IDs that must exist before cluster/node-group create and
    be destroyed only after cluster/node-group destroy (ordering via depends_on).
  EOT
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

variable "master_min_resource_preset_id" {
  description = <<-EOT
    Optional Managed Kubernetes master scale_policy.auto_scale.min_resource_preset_id
    (e.g. s-c2-m8). This is the MINIMUM master resource profile, not a maximum cap —
    the platform may scale the master above this floor when needed.
    null = omit scale_policy (platform default; preserves staging/production behavior).
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.master_min_resource_preset_id == null || length(trimspace(var.master_min_resource_preset_id)) > 0
    error_message = "master_min_resource_preset_id must be null or a non-empty preset id (e.g. s-c2-m8)."
  }
}

variable "master_auto_upgrade" {
  description = "Master maintenance_policy.auto_upgrade. Disable for short cloud experiments."
  type        = bool
  default     = true
}

variable "node_auto_upgrade" {
  description = "CPU node group auto_upgrade. Disable for short cloud experiments."
  type        = bool
  default     = true
}

variable "node_auto_repair" {
  description = "CPU node group auto_repair."
  type        = bool
  default     = true
}

variable "cpu_deploy_max_expansion" {
  description = "Node group deploy_policy.max_expansion. Use 0 when Compute quotas leave no room for a surge node."
  type        = number
  default     = null

  validation {
    condition     = var.cpu_deploy_max_expansion == null || (var.cpu_deploy_max_expansion >= 0 && var.cpu_deploy_max_expansion <= 10)
    error_message = "cpu_deploy_max_expansion must be null or 0..10."
  }
}

variable "cpu_deploy_max_unavailable" {
  description = "Node group deploy_policy.max_unavailable. Pair with max_expansion=0 under tight quotas."
  type        = number
  default     = null

  validation {
    condition     = var.cpu_deploy_max_unavailable == null || (var.cpu_deploy_max_unavailable >= 0 && var.cpu_deploy_max_unavailable <= 10)
    error_message = "cpu_deploy_max_unavailable must be null or 0..10."
  }
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

variable "cpu_node_labels" {
  description = "Kubernetes node labels for CPU workers (scheduling)."
  type        = map(string)
  default = {
    "workload.credit-scoring/type" = "cpu"
    "workload.credit-scoring/role" = "serving"
  }
}

variable "cpu_enable_autoscaling" {
  description = "Use auto_scale instead of fixed_scale for CPU node group."
  type        = bool
  default     = false
}

variable "cpu_autoscaling_min" {
  type    = number
  default = 1
}

variable "cpu_autoscaling_max" {
  type    = number
  default = 3
}

variable "cpu_autoscaling_initial" {
  type    = number
  default = 1
}

# --- Optional GPU node group (OFF by default; never enable without budget approval) ---

variable "enable_gpu_node_group" {
  description = "Create a GPU node group. Default false to avoid cloud spend. NOT applied in CI."
  type        = bool
  default     = false
}

variable "gpu_node_group_name" {
  type    = string
  default = "gpu-workers"
}

variable "gpu_node_count" {
  type    = number
  default = 1

  validation {
    condition     = var.gpu_node_count >= 1 && var.gpu_node_count <= 3
    error_message = "gpu_node_count must be between 1 and 3."
  }
}

variable "gpu_platform_id" {
  description = "GPU platform id (verify availability in folder/zone before enable)."
  type        = string
  default     = "gpu-standard-v3"
}

variable "gpu_count" {
  description = "Number of GPUs per node (provider attribute resources.gpus)."
  type        = number
  default     = 1

  validation {
    condition     = var.gpu_count >= 1 && var.gpu_count <= 8
    error_message = "gpu_count must be between 1 and 8."
  }
}

variable "gpu_node_cores" {
  type    = number
  default = 8
}

variable "gpu_node_memory_gb" {
  type    = number
  default = 48
}

variable "gpu_disk_type" {
  type    = string
  default = "network-ssd"
}

variable "gpu_disk_size_gb" {
  type    = number
  default = 100
}

variable "gpu_preemptible" {
  type    = bool
  default = false
}

variable "gpu_zone" {
  description = "Optional zone override for GPU nodes (empty = master_zone)."
  type        = string
  default     = ""
}

variable "gpu_environment" {
  description = "Provider gpu_settings.gpu_environment: runc | runc_drivers_cuda | empty to omit block."
  type        = string
  default     = "runc_drivers_cuda"

  validation {
    condition = contains(
      ["", "runc", "runc_drivers_cuda"],
      var.gpu_environment
    )
    error_message = "gpu_environment must be empty, runc, or runc_drivers_cuda."
  }
}

variable "gpu_node_labels" {
  type = map(string)
  default = {
    "workload.credit-scoring/type" = "gpu"
    "workload.credit-scoring/role" = "training"
    "nvidia.com/gpu"               = "true"
  }
}

variable "gpu_node_taints" {
  description = "Taints so only GPU-tolerant pods schedule here (format key=value:Effect)."
  type        = list(string)
  default = [
    "nvidia.com/gpu=true:NoSchedule",
    "workload.credit-scoring/gpu=true:NoSchedule",
  ]
}
