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
