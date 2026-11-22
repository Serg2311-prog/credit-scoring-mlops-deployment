variable "name_prefix" {
  description = "Prefix for service account names."
  type        = string
}

variable "folder_id" {
  description = "Folder where service accounts and role bindings are created."
  type        = string
}

variable "labels" {
  description = "Labels for service accounts."
  type        = map(string)
  default     = {}
}

variable "enable_load_balancer_admin" {
  description = <<-EOT
    Grant load-balancer.admin to the cluster SA.
    Needed only when creating Yandex Load Balancer / Ingress that uses cloud LB.
    Default false to keep privileges minimal until Ingress is introduced.
  EOT
  type        = bool
  default     = false
}
