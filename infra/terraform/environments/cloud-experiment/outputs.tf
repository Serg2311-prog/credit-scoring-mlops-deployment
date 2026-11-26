output "environment" {
  value = "cloud-experiment"
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

output "cpu_node_group_id" {
  value = module.kubernetes.node_group_id
}

output "gpu_node_group_enabled" {
  value = module.kubernetes.gpu_node_group_enabled
}

output "network_policy_provider" {
  value = module.kubernetes.network_policy_provider
}

output "registry_id" {
  value = var.enable_registry ? module.registry[0].registry_id : null
}

output "artifacts_bucket" {
  value = var.enable_storage ? module.storage[0].bucket_name : null
}

output "log_group_id" {
  value = var.enable_monitoring ? module.monitoring[0].log_group_id : null
}

output "iam_boundaries" {
  value = module.iam.iam_boundary_notes
}

output "ml_reader_sa_id" {
  value = module.iam.ml_reader_sa_id
}

output "registry_pusher_sa_id" {
  value = module.iam.registry_pusher_sa_id
}

output "experiment_guards" {
  value = {
    zone                          = var.zone
    kubernetes_version            = var.kubernetes_version
    release_channel               = "REGULAR"
    master_min_resource_preset_id = "s-c2-m8"
    node_count                    = var.node_count
    node_cores                    = var.node_cores
    node_memory_gb                = var.node_memory_gb
    node_disk_size_gb             = var.node_disk_size_gb
    node_preemptible              = var.node_preemptible
    cpu_enable_autoscaling        = var.cpu_enable_autoscaling
    enable_gpu_node_group         = var.enable_gpu_node_group
    cpu_deploy_max_expansion      = 0
    cpu_deploy_max_unavailable    = 1
    enable_registry               = var.enable_registry
    enable_storage                = var.enable_storage
    enable_monitoring             = var.enable_monitoring
    enable_ml_reader_sa           = false
    enable_registry_pusher_sa     = false
  }
}
