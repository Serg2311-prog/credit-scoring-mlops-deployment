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
  value = yandex_kubernetes_node_group.cpu.id
}

output "kubeconfig_hint" {
  description = "Command to fetch kubeconfig after apply (not executed in stage 3B)."
  value       = "yc managed-kubernetes cluster get-credentials --id ${yandex_kubernetes_cluster.this.id} --external|--internal"
}
