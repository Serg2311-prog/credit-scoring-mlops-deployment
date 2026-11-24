output "environment" {
  value = "staging"
}

output "network_id" {
  value = module.network.network_id
}

output "subnet_ids" {
  value = module.network.subnet_ids
}

output "k8s_cluster_id" {
  value = module.kubernetes.cluster_id
}

output "registry_id" {
  value = module.registry.registry_id
}

output "artifacts_bucket" {
  value = module.storage.bucket_name
}

output "log_group_id" {
  value = module.monitoring.log_group_id
}

output "image_name_examples" {
  value = module.registry.image_name_examples
}

output "iam_boundaries" {
  value = module.iam.iam_boundary_notes
}

output "metrics_notes" {
  value = module.monitoring.metrics_integration_notes
}

output "cpu_node_group_id" {
  value = module.kubernetes.node_group_id
}

output "gpu_node_group_enabled" {
  value = module.kubernetes.gpu_node_group_enabled
}

output "gpu_node_group_id" {
  value = module.kubernetes.gpu_node_group_id
}

output "network_policy_provider" {
  value = module.kubernetes.network_policy_provider
}
