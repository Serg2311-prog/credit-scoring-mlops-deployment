variable "cloud_id" {
  description = "Yandex Cloud ID (from env/tfvars; never commit real values)."
  type        = string
}

variable "folder_id" {
  description = "Experiment folder ID (prefer dedicated folder)."
  type        = string
}

variable "zone" {
  description = "Zonal master + single worker zone."
  type        = string
  default     = "ru-central1-a"

  validation {
    condition     = var.zone == "ru-central1-a"
    error_message = "cloud-experiment is locked to ru-central1-a (confirmed quotas)."
  }
}

variable "name_prefix" {
  type    = string
  default = "cs-exp"
}

variable "k8s_api_allowed_cidrs" {
  description = "Admin CIDRs for Kubernetes API. Must be non-empty before plan/apply; IPv4 /1–/32 only."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for c in var.k8s_api_allowed_cidrs : (
        length(trimspace(c)) > 0 &&
        can(cidrnetmask(c)) &&
        !can(regex(":", c)) &&
        tonumber(split("/", c)[1]) >= 1 &&
        tonumber(split("/", c)[1]) <= 32
      )
    ])
    error_message = "Each k8s_api_allowed_cidrs entry must be a non-empty IPv4 CIDR with prefix /1–/32 (never /0)."
  }
}

variable "kubernetes_version" {
  description = "Must be available on REGULAR channel (verified: 1.32–1.35)."
  type        = string
  default     = "1.34"

  validation {
    condition     = contains(["1.32", "1.33", "1.34", "1.35"], var.kubernetes_version)
    error_message = "kubernetes_version must be one of 1.32–1.35 for this experiment."
  }
}

# --- Hard locks matching confirmed Compute quotas (4 vCPU / 16 GB / 64 GiB) ---

variable "node_count" {
  type    = number
  default = 1

  validation {
    condition     = var.node_count == 1
    error_message = "cloud-experiment allows exactly 1 worker (quota + budget)."
  }
}

variable "node_cores" {
  type    = number
  default = 4

  validation {
    condition     = var.node_cores == 4
    error_message = "cloud-experiment node_cores locked to 4 (quota ceiling)."
  }
}

variable "node_memory_gb" {
  type    = number
  default = 16

  validation {
    condition     = var.node_memory_gb == 16
    error_message = "cloud-experiment node_memory_gb locked to 16 (quota ceiling)."
  }
}

variable "node_disk_size_gb" {
  type    = number
  default = 64

  validation {
    condition     = var.node_disk_size_gb == 64
    error_message = "cloud-experiment node_disk_size_gb locked to 64 GiB (quota ceiling)."
  }
}

variable "node_preemptible" {
  type    = bool
  default = false

  validation {
    condition     = var.node_preemptible == false
    error_message = "cloud-experiment requires non-preemptible worker."
  }
}

variable "public_master_ip" {
  type    = bool
  default = true

  validation {
    condition     = var.public_master_ip == true
    error_message = "Experiment needs public master endpoint (CIDR-restricted)."
  }
}

variable "cpu_enable_autoscaling" {
  type    = bool
  default = false

  validation {
    condition     = var.cpu_enable_autoscaling == false
    error_message = "Node autoscaling forbidden under 4 vCPU / 16 GB quota."
  }
}

variable "enable_gpu_node_group" {
  type    = bool
  default = false

  validation {
    condition     = var.enable_gpu_node_group == false
    error_message = "GPU node group is forbidden for cloud-experiment (quota + budget)."
  }
}

variable "enable_load_balancer_admin" {
  description = "IAM loadBalancer.admin for Ingress LB. Default false until Ingress is required."
  type        = bool
  default     = false
}

variable "enable_registry" {
  description = "Create Yandex Container Registry. Prefer GHCR for experiment (cost)."
  type        = bool
  default     = false
}

variable "enable_storage" {
  description = "Create artifacts Object Storage + optional KMS. Not required for short experiment."
  type        = bool
  default     = false
}

variable "enable_monitoring" {
  description = "Create Cloud Logging group + master logging. Optional cost."
  type        = bool
  default     = false
}

variable "artifacts_bucket_name" {
  description = "Required only when enable_storage=true."
  type        = string
  default     = ""
}

variable "log_retention_days" {
  type    = number
  default = 1
}

variable "extra_labels" {
  type    = map(string)
  default = {}
}
