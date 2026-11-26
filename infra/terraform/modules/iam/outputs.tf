output "k8s_cluster_sa_id" {
  description = "Service account ID for Managed Kubernetes cluster."
  value       = yandex_iam_service_account.k8s_cluster.id
}

output "k8s_nodes_sa_id" {
  description = "Service account ID for Kubernetes node groups."
  value       = yandex_iam_service_account.k8s_nodes.id
}

output "ml_reader_sa_id" {
  description = "Service account ID for read-only ML artifact access; null when disabled."
  value       = try(yandex_iam_service_account.ml_reader[0].id, null)
}

output "registry_pusher_sa_id" {
  description = "Service account ID for pushing images to Container Registry; null when disabled."
  value       = try(yandex_iam_service_account.registry_pusher[0].id, null)
}

output "k8s_cluster_sa_member" {
  description = "IAM member string for cluster SA."
  value       = "serviceAccount:${yandex_iam_service_account.k8s_cluster.id}"
}

output "role_bindings_ready" {
  description = "Dependency handle: IAM bindings that must exist before cluster creation."
  value = concat(
    [for r in yandex_resourcemanager_folder_iam_member.k8s_cluster : r.id],
    [for r in yandex_resourcemanager_folder_iam_member.k8s_nodes : r.id],
  )
}

output "iam_boundary_notes" {
  description = "Human-readable privilege boundaries (for docs)."
  value = {
    k8s_cluster_required = "k8s.clusters.agent + vpc.publicAdmin"
    k8s_cluster_optional = "registry puller / logging.writer / LB admin (flags)"
    k8s_nodes            = "optional registry puller + logging.writer"
    ml_reader            = var.enable_ml_reader_sa ? "storage.viewer only" : "disabled"
    registry_pusher      = var.enable_registry_pusher_sa ? "container-registry.images.pusher only" : "disabled"
    not_granted          = "editor, admin, storage.admin, cloud-wide roles"
  }
}
