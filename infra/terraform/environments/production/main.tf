locals {
  environment = "production"
  labels = merge(
    {
      project     = "credit-scoring"
      environment = local.environment
      managed-by  = "terraform"
      stage       = "3b"
    },
    var.extra_labels
  )
}

module "network" {
  source = "../../modules/network"

  name_prefix             = var.name_prefix
  folder_id               = var.folder_id
  labels                  = local.labels
  k8s_api_allowed_cidrs   = var.k8s_api_allowed_cidrs
  enable_nodeport_ingress = false

  # Production CIDR space — intentionally different from staging (10.20.0.0/24).
  subnets = [
    {
      name = "a"
      zone = var.zone
      cidr = "10.30.0.0/24"
    }
  ]
}

module "iam" {
  source = "../../modules/iam"

  name_prefix                = var.name_prefix
  folder_id                  = var.folder_id
  labels                     = local.labels
  enable_load_balancer_admin = var.enable_load_balancer_admin
}

module "monitoring" {
  source = "../../modules/monitoring"

  name_prefix        = var.name_prefix
  folder_id          = var.folder_id
  labels             = local.labels
  environment        = local.environment
  log_retention_days = var.log_retention_days
}

module "registry" {
  source = "../../modules/registry"

  name_prefix = var.name_prefix
  folder_id   = var.folder_id
  labels      = local.labels
}

module "storage" {
  source = "../../modules/storage"

  name_prefix           = var.name_prefix
  folder_id             = var.folder_id
  bucket_name           = var.artifacts_bucket_name
  labels                = local.labels
  enable_versioning     = true
  enable_kms_encryption = true
  max_size_bytes        = 21474836480 # 20 GiB soft cap
}

module "kubernetes" {
  source = "../../modules/kubernetes"

  name_prefix                = var.name_prefix
  folder_id                  = var.folder_id
  network_id                 = module.network.network_id
  subnet_id                  = module.network.subnet_ids["a"]
  master_zone                = var.zone
  master_security_group_ids  = [module.network.master_security_group_id]
  node_security_group_ids    = [module.network.nodes_security_group_id]
  cluster_service_account_id = module.iam.k8s_cluster_sa_id
  node_service_account_id    = module.iam.k8s_nodes_sa_id
  iam_dependency_ids         = module.iam.role_bindings_ready
  labels                     = local.labels
  kubernetes_version         = var.kubernetes_version
  release_channel            = "STABLE"
  public_ip                  = var.public_master_ip
  log_group_id               = module.monitoring.log_group_id
  enable_master_logging      = true
  node_count                 = var.node_count
  node_cores                 = var.node_cores
  node_memory_gb             = var.node_memory_gb
  node_preemptible           = var.node_preemptible
  node_disk_size_gb          = 100
  node_platform_id           = "standard-v3"
}
