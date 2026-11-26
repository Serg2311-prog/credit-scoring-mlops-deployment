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
    CIDR blocks allowed to reach Kubernetes API (TCP 443/6443) on the master SG.
    Empty list means NO public/internet API ingress is opened.
    Each entry must be a non-empty IPv4 CIDR with prefix length 1–32 (never /0).
  EOT
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for c in var.k8s_api_allowed_cidrs : (
        length(trimspace(c)) > 0 &&
        c != "0.0.0.0/0" &&
        can(cidrnetmask(c)) &&
        !can(regex(":", c)) &&
        tonumber(split("/", c)[1]) >= 1 &&
        tonumber(split("/", c)[1]) <= 32
      )
    ])
    error_message = "Each k8s_api_allowed_cidrs entry must be a non-empty IPv4 CIDR with prefix /1–/32 (0.0.0.0/0 and empty values forbidden)."
  }
}

variable "enable_nodeport_ingress" {
  description = "If true, allow NodePort range 30000-32767 from k8s_api_allowed_cidrs only (still not 0.0.0.0/0)."
  type        = bool
  default     = false
}

variable "cluster_ipv4_range" {
  description = <<-EOT
    Pod (cluster) IPv4 CIDR allowed on node SG.
    Must match the live Managed Kubernetes ip_allocation_policy.cluster_ipv4_cidr_block.
    Yandex default observed in cloud-experiment: 10.112.0.0/16.
  EOT
  type        = string
  default     = "10.112.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.cluster_ipv4_range))
    error_message = "cluster_ipv4_range must be a valid IPv4 CIDR."
  }
}

variable "service_ipv4_range" {
  description = <<-EOT
    Service IPv4 CIDR allowed on node SG.
    Must match ip_allocation_policy.service_ipv4_cidr_block.
    Yandex default observed in cloud-experiment: 10.96.0.0/16.
  EOT
  type        = string
  default     = "10.96.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.service_ipv4_range))
    error_message = "service_ipv4_range must be a valid IPv4 CIDR."
  }
}
