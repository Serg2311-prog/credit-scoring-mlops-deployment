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

variable "enable_ml_reader_sa" {
  description = "Create ml-reader SA + storage.viewer binding. Default true (staging/production)."
  type        = bool
  default     = true
}

variable "enable_registry_pusher_sa" {
  description = "Create registry-pusher SA + images.pusher binding. Default true (staging/production)."
  type        = bool
  default     = true
}

variable "grant_container_registry_puller" {
  description = <<-EOT
    Grant container-registry.images.puller to cluster and node SAs.
    Required when pulling from Yandex Container Registry. Safe to disable when
    images come only from GHCR/Docker Hub (static credentials / imagePullSecrets).
    Default true for staging/production compatibility.
  EOT
  type        = bool
  default     = true
}

variable "grant_logging_writer" {
  description = <<-EOT
    Grant logging.writer to cluster and node SAs.
    Required for Cloud Logging / master logging. Disable when monitoring module is off.
    Default true for staging/production compatibility.
  EOT
  type        = bool
  default     = true
}
