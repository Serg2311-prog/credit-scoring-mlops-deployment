output "cluster_id" {
  value = yandex_kubernetes_cluster.this.id
}

output "cluster_name" {
  value = yandex_kubernetes_cluster.this.name
}

output "cluster_status" {
  value = yandex_kubernetes_cluster.this.status
}

output "internal_v4_endpoint" {
  value = try(yandex_kubernetes_cluster.this.master[0].internal_v4_endpoint, null)
}

output "external_v4_endpoint" {
  value = try(yandex_kubernetes_cluster.this.master[0].external_v4_endpoint, null)
}

output "node_group_id" {
  description = "CPU node group id (default serving)."
  value       = yandex_kubernetes_node_group.cpu.id
}

output "gpu_node_group_id" {
  description = "GPU node group id when enable_gpu_node_group=true; otherwise null."
  value       = try(yandex_kubernetes_node_group.gpu[0].id, null)
}

output "gpu_node_group_enabled" {
  value = var.enable_gpu_node_group
}

output "network_policy_provider" {
  value = var.network_policy_provider
}

output "kubeconfig_hint" {
  description = "Command to fetch kubeconfig after apply (cloud apply NOT executed in course policy)."
  value       = "yc managed-kubernetes cluster get-credentials --id ${yandex_kubernetes_cluster.this.id} --external|--internal"
}
