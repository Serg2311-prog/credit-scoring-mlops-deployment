resource "yandex_kubernetes_cluster" "this" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-k8s"
  description = "Credit scoring Managed Kubernetes (${var.name_prefix})"

  network_id = var.network_id

  master {
    version = var.kubernetes_version

    zonal {
      zone      = var.master_zone
      subnet_id = var.subnet_id
    }

    public_ip          = var.public_ip
    security_group_ids = var.master_security_group_ids

    # min_resource_preset_id is a floor (minimum profile), not a hard maximum.
    dynamic "scale_policy" {
      for_each = var.master_min_resource_preset_id != null ? [1] : []
      content {
        auto_scale {
          min_resource_preset_id = var.master_min_resource_preset_id
        }
      }
    }

    maintenance_policy {
      auto_upgrade = var.master_auto_upgrade

      maintenance_window {
        day        = "sunday"
        start_time = "03:00"
        duration   = "3h"
      }
    }

    dynamic "master_logging" {
      for_each = var.enable_master_logging && var.log_group_id != "" ? [1] : []
      content {
        enabled                    = true
        log_group_id               = var.log_group_id
        kube_apiserver_enabled     = true
        cluster_autoscaler_enabled = true
        events_enabled             = true
        audit_enabled              = true
      }
    }
  }

  service_account_id      = var.cluster_service_account_id
  node_service_account_id = var.node_service_account_id

  release_channel         = var.release_channel
  network_policy_provider = var.network_policy_provider

  labels = var.labels

  # IAM + SG rules before create; reverse on destroy (cluster before rule teardown).
  depends_on = [terraform_data.iam_ready, terraform_data.sg_rules_ready]
}

resource "terraform_data" "iam_ready" {
  input = var.iam_dependency_ids
}

resource "terraform_data" "sg_rules_ready" {
  input = var.security_group_dependency_ids
}

resource "yandex_kubernetes_node_group" "cpu" {
  cluster_id  = yandex_kubernetes_cluster.this.id
  name        = "${var.name_prefix}-${var.node_group_name}"
  description = "CPU workers for credit-scoring API (default serving path)"
  version     = var.kubernetes_version

  labels      = var.labels
  node_labels = var.cpu_node_labels

  instance_template {
    platform_id = var.node_platform_id

    network_interface {
      nat                = true
      subnet_ids         = [var.subnet_id]
      security_group_ids = var.node_security_group_ids
    }

    resources {
      cores         = var.node_cores
      memory        = var.node_memory_gb
      core_fraction = var.node_core_fraction
      gpus          = 0
    }

    boot_disk {
      type = var.node_disk_type
      size = var.node_disk_size_gb
    }

    scheduling_policy {
      preemptible = var.node_preemptible
    }

    container_runtime {
      type = "containerd"
    }
  }

  scale_policy {
    dynamic "fixed_scale" {
      for_each = var.cpu_enable_autoscaling ? [] : [1]
      content {
        size = var.node_count
      }
    }

    dynamic "auto_scale" {
      for_each = var.cpu_enable_autoscaling ? [1] : []
      content {
        min     = var.cpu_autoscaling_min
        max     = var.cpu_autoscaling_max
        initial = var.cpu_autoscaling_initial
      }
    }
  }

  allocation_policy {
    location {
      zone = var.master_zone
    }
  }

  dynamic "deploy_policy" {
    for_each = var.cpu_deploy_max_expansion != null || var.cpu_deploy_max_unavailable != null ? [1] : []
    content {
      max_expansion   = coalesce(var.cpu_deploy_max_expansion, 0)
      max_unavailable = coalesce(var.cpu_deploy_max_unavailable, 1)
    }
  }

  maintenance_policy {
    auto_upgrade = var.node_auto_upgrade
    auto_repair  = var.node_auto_repair

    maintenance_window {
      day        = "sunday"
      start_time = "04:00"
      duration   = "3h"
    }
  }

  # Ensure SG rules (esp. Nodes↔Master) exist before workers register.
  depends_on = [terraform_data.sg_rules_ready]
}

# GPU workers — DISABLED BY DEFAULT (enable_gpu_node_group=false).
# Attributes verified against yandex provider schema (resources.gpus, gpu_settings,
# node_labels, node_taints). Do not enable without budget approval; never applied in CI.
resource "yandex_kubernetes_node_group" "gpu" {
  count = var.enable_gpu_node_group ? 1 : 0

  cluster_id  = yandex_kubernetes_cluster.this.id
  name        = "${var.name_prefix}-${var.gpu_node_group_name}"
  description = "Optional GPU workers (opt-in; costly). Not used by default serving."
  version     = var.kubernetes_version

  labels      = var.labels
  node_labels = var.gpu_node_labels
  node_taints = var.gpu_node_taints

  instance_template {
    platform_id = var.gpu_platform_id

    network_interface {
      nat                = true
      subnet_ids         = [var.subnet_id]
      security_group_ids = var.node_security_group_ids
    }

    resources {
      cores         = var.gpu_node_cores
      memory        = var.gpu_node_memory_gb
      core_fraction = 100
      gpus          = var.gpu_count
    }

    dynamic "gpu_settings" {
      for_each = var.gpu_environment == "" ? [] : [1]
      content {
        gpu_environment = var.gpu_environment
      }
    }

    boot_disk {
      type = var.gpu_disk_type
      size = var.gpu_disk_size_gb
    }

    scheduling_policy {
      preemptible = var.gpu_preemptible
    }

    container_runtime {
      type = "containerd"
    }
  }

  scale_policy {
    fixed_scale {
      size = var.gpu_node_count
    }
  }

  allocation_policy {
    location {
      zone = var.gpu_zone != "" ? var.gpu_zone : var.master_zone
    }
  }

  maintenance_policy {
    auto_upgrade = true
    auto_repair  = true

    maintenance_window {
      day        = "sunday"
      start_time = "05:00"
      duration   = "3h"
    }
  }
}
