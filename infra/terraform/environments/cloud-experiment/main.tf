locals {
  environment = "cloud-experiment"
  labels = merge(
    {
      project     = "credit-scoring"
      environment = local.environment
      managed-by  = "terraform"
      stage       = "11-7"
      budget      = "grant-experiment"
    },
    var.extra_labels
  )
}

# Soft quota reminder: worker alone exhausts confirmed Compute quotas in ru-central1-a.
# Managed Kubernetes master is billed separately and typically does not consume
# Compute Cloud instance quotas — confirm in console before apply.
resource "terraform_data" "quota_guard" {
  input = {
    zone           = var.zone
    node_cores     = var.node_cores
    node_memory_gb = var.node_memory_gb
    node_disk_gb   = var.node_disk_size_gb
    node_count     = var.node_count
  }

  lifecycle {
    precondition {
      condition = (
        var.node_count == 1 &&
        var.node_cores == 4 &&
        var.node_memory_gb == 16 &&
        var.node_disk_size_gb == 64 &&
        var.enable_gpu_node_group == false &&
        var.cpu_enable_autoscaling == false
      )
      error_message = "Quota guard failed: experiment must be 1×(4c/16g/64ssd), no GPU, no autoscaling."
    }

    precondition {
      condition     = length(var.k8s_api_allowed_cidrs) > 0
      error_message = "Set k8s_api_allowed_cidrs to your admin IP/32 before plan/apply (never 0.0.0.0/0)."
    }
  }
}

module "network" {
  source = "../../modules/network"

  name_prefix             = var.name_prefix
  folder_id               = var.folder_id
  labels                  = local.labels
  k8s_api_allowed_cidrs   = var.k8s_api_allowed_cidrs
  enable_nodeport_ingress = false

  # Non-overlapping with staging 10.20.0.0/24 and production ranges.
  subnets = [
    {
      name = "a"
      zone = var.zone
      cidr = "10.40.0.0/24"
    }
  ]
}

module "iam" {
  source = "../../modules/iam"

  name_prefix                     = var.name_prefix
  folder_id                       = var.folder_id
  labels                          = local.labels
  enable_load_balancer_admin      = var.enable_load_balancer_admin
  enable_ml_reader_sa             = false
  enable_registry_pusher_sa       = false
  grant_container_registry_puller = var.enable_registry
  grant_logging_writer            = var.enable_monitoring
}

module "monitoring" {
  count  = var.enable_monitoring ? 1 : 0
  source = "../../modules/monitoring"

  name_prefix        = var.name_prefix
  folder_id          = var.folder_id
  labels             = local.labels
  environment        = local.environment
  log_retention_days = var.log_retention_days
}

module "registry" {
  count  = var.enable_registry ? 1 : 0
  source = "../../modules/registry"

  name_prefix = var.name_prefix
  folder_id   = var.folder_id
  labels      = local.labels
}

module "storage" {
  count  = var.enable_storage ? 1 : 0
  source = "../../modules/storage"

  name_prefix           = var.name_prefix
  folder_id             = var.folder_id
  bucket_name           = var.artifacts_bucket_name
  labels                = local.labels
  enable_versioning     = true
  enable_kms_encryption = false
  max_size_bytes        = 1073741824 # 1 GiB soft cap
}

module "kubernetes" {
  source = "../../modules/kubernetes"

  name_prefix                   = var.name_prefix
  folder_id                     = var.folder_id
  network_id                    = module.network.network_id
  subnet_id                     = module.network.subnet_ids["a"]
  master_zone                   = var.zone
  master_security_group_ids     = [module.network.master_security_group_id]
  node_security_group_ids       = [module.network.nodes_security_group_id]
  cluster_service_account_id    = module.iam.k8s_cluster_sa_id
  node_service_account_id       = module.iam.k8s_nodes_sa_id
  iam_dependency_ids            = module.iam.role_bindings_ready
  security_group_dependency_ids = module.network.security_group_rule_ids
  labels                        = local.labels
  kubernetes_version            = var.kubernetes_version
  release_channel               = "REGULAR"
  public_ip                     = var.public_master_ip
  log_group_id                  = var.enable_monitoring ? module.monitoring[0].log_group_id : ""
  enable_master_logging         = var.enable_monitoring
  # Minimum master profile (floor), not a maximum resource limit.
  master_min_resource_preset_id = "s-c2-m8"
  # Freeze upgrades during short experiment window.
  master_auto_upgrade = false
  node_auto_upgrade   = false
  node_auto_repair    = true
  # Worker saturates Compute quota — forbid surge node on replace/upgrade.
  cpu_deploy_max_expansion   = 0
  cpu_deploy_max_unavailable = 1
  node_count                 = var.node_count
  node_cores                 = var.node_cores
  node_memory_gb             = var.node_memory_gb
  node_preemptible           = var.node_preemptible
  node_disk_size_gb          = var.node_disk_size_gb
  node_platform_id           = "standard-v3"
  node_core_fraction         = 100
  cpu_enable_autoscaling     = var.cpu_enable_autoscaling
  enable_gpu_node_group      = var.enable_gpu_node_group

  depends_on = [terraform_data.quota_guard]
}
