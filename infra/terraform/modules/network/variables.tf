variable "name_prefix" {
  description = "Prefix for network resource names (e.g. cs-staging)."
  type        = string
}

variable "folder_id" {
  description = "Yandex Cloud folder ID."
  type        = string
}

variable "labels" {
  description = "Labels applied to network resources."
  type        = map(string)
  default     = {}
}

variable "network_description" {
  description = "Optional VPC description."
  type        = string
  default     = "Credit scoring VPC"
}

variable "subnets" {
  description = <<-EOT
    Subnets to create. CIDRs must not overlap.
    Example: [{ name = "a", zone = "ru-central1-a", cidr = "10.10.0.0/24" }]
  EOT
  type = list(object({
    name = string
    zone = string
    cidr = string
  }))

  validation {
    condition     = length(var.subnets) >= 1
    error_message = "At least one subnet is required."
  }
}

variable "k8s_api_allowed_cidrs" {
  description = <<-EOT
    CIDR blocks allowed to reach Kubernetes API (TCP 443) on the master SG.
    Empty list means NO public/internet API ingress is opened.
    Do not use 0.0.0.0/0 unless explicitly approved for a short-lived exception.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for c in var.k8s_api_allowed_cidrs : c != "0.0.0.0/0"
    ])
    error_message = "Opening Kubernetes API to 0.0.0.0/0 is forbidden by default. Use a narrow admin CIDR."
  }
}

variable "enable_nodeport_ingress" {
  description = "If true, allow NodePort range 30000-32767 from k8s_api_allowed_cidrs only (still not 0.0.0.0/0)."
  type        = bool
  default     = false
}
