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

    maintenance_policy {
      auto_upgrade = true

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

  # Ensure IAM bindings exist before cluster create / are destroyed after cluster.
  depends_on = [terraform_data.iam_ready]
}

resource "terraform_data" "iam_ready" {
  input = var.iam_dependency_ids
}

resource "yandex_kubernetes_node_group" "cpu" {
  cluster_id  = yandex_kubernetes_cluster.this.id
  name        = "${var.name_prefix}-${var.node_group_name}"
  description = "CPU-only workers for credit-scoring API"
  version     = var.kubernetes_version

  labels = var.labels

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
    fixed_scale {
      size = var.node_count
    }
  }

  allocation_policy {
    location {
      zone = var.master_zone
    }
  }

  maintenance_policy {
    auto_upgrade = true
    auto_repair  = true

    maintenance_window {
      day        = "sunday"
      start_time = "04:00"
      duration   = "3h"
    }
  }
}
