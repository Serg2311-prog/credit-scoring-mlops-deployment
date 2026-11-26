# Native Terraform tests (mock_provider) — no cloud API calls.
# Run from module dir:
#   terraform -chdir=infra/terraform/modules/kubernetes init -backend=false
#   terraform -chdir=infra/terraform/modules/kubernetes test

mock_provider "yandex" {
  mock_resource "yandex_kubernetes_cluster" {
    defaults = {
      id     = "catestcluster000000000000"
      status = "RUNNING"
      name   = "cs-test-k8s"
    }
  }

  mock_resource "yandex_kubernetes_node_group" {
    defaults = {
      id   = "catestnodegroup00000000000"
      name = "cs-test-workers"
    }
  }
}

variables {
  name_prefix                = "cs-test"
  folder_id                  = "b1g00000000000000000"
  network_id                 = "enp00000000000000000"
  subnet_id                  = "e9b00000000000000000"
  master_zone                = "ru-central1-a"
  master_security_group_ids  = ["enpsgmaster000000000"]
  node_security_group_ids    = ["enpsgnodes0000000000"]
  cluster_service_account_id = "aje00000000000000000"
  node_service_account_id    = "aje00000000000000001"
  log_group_id               = ""
  enable_master_logging      = false
  public_ip                  = false
  node_count                 = 1
  node_cores                 = 2
  node_memory_gb             = 4
  node_preemptible           = true
  node_platform_id           = "standard-v3"
  cpu_enable_autoscaling     = false
  enable_gpu_node_group      = false
  network_policy_provider    = "CALICO"
}

run "gpu_disabled_by_default" {
  command = plan

  assert {
    condition     = length(yandex_kubernetes_node_group.gpu) == 0
    error_message = "GPU node group must be absent when enable_gpu_node_group=false"
  }

  assert {
    condition     = yandex_kubernetes_node_group.cpu.name == "cs-test-cpu-workers"
    error_message = "CPU node group must be planned"
  }

  assert {
    condition     = yandex_kubernetes_node_group.cpu.node_labels["workload.credit-scoring/type"] == "cpu"
    error_message = "CPU node_labels missing type=cpu"
  }

  assert {
    condition     = yandex_kubernetes_cluster.this.network_policy_provider == "CALICO"
    error_message = "Managed Kubernetes must use CALICO"
  }

  assert {
    condition     = yandex_kubernetes_node_group.cpu.instance_template[0].resources[0].gpus == 0
    error_message = "CPU workers must have gpus=0"
  }

  assert {
    condition     = length(yandex_kubernetes_cluster.this.master[0].scale_policy) == 0
    error_message = "scale_policy must be omitted when master_min_resource_preset_id is null"
  }
}

run "master_min_preset_scale_policy" {
  command = plan

  variables {
    master_min_resource_preset_id = "s-c2-m8"
  }

  assert {
    condition = (
      length(yandex_kubernetes_cluster.this.master[0].scale_policy) == 1 &&
      yandex_kubernetes_cluster.this.master[0].scale_policy[0].auto_scale[0].min_resource_preset_id == "s-c2-m8"
    )
    error_message = "master scale_policy.auto_scale.min_resource_preset_id must be s-c2-m8 when set"
  }
}

run "cpu_autoscaling_plan" {
  command = plan

  variables {
    cpu_enable_autoscaling  = true
    cpu_autoscaling_min     = 1
    cpu_autoscaling_max     = 3
    cpu_autoscaling_initial = 1
  }

  assert {
    condition     = length(yandex_kubernetes_node_group.cpu.scale_policy[0].auto_scale) == 1
    error_message = "CPU auto_scale block expected when cpu_enable_autoscaling=true"
  }

  assert {
    condition     = length(yandex_kubernetes_node_group.cpu.scale_policy[0].fixed_scale) == 0
    error_message = "fixed_scale must be empty when autoscaling"
  }
}

run "gpu_enabled_explicitly" {
  command = plan

  variables {
    enable_gpu_node_group = true
    gpu_count             = 1
    gpu_node_count        = 1
    gpu_platform_id       = "gpu-standard-v3"
  }

  assert {
    condition     = length(yandex_kubernetes_node_group.gpu) == 1
    error_message = "GPU node group must exist when enable_gpu_node_group=true"
  }

  assert {
    condition     = yandex_kubernetes_node_group.gpu[0].instance_template[0].resources[0].gpus == 1
    error_message = "GPU resources.gpus must be 1"
  }

  assert {
    condition     = yandex_kubernetes_node_group.gpu[0].instance_template[0].platform_id == "gpu-standard-v3"
    error_message = "GPU platform_id mismatch"
  }

  assert {
    condition     = contains(yandex_kubernetes_node_group.gpu[0].node_taints, "nvidia.com/gpu=true:NoSchedule")
    error_message = "GPU node_taints must include nvidia.com/gpu NoSchedule"
  }

  assert {
    condition     = yandex_kubernetes_node_group.gpu[0].node_labels["workload.credit-scoring/type"] == "gpu"
    error_message = "GPU node_labels type=gpu required"
  }

  assert {
    condition     = length(yandex_kubernetes_node_group.cpu) >= 1 || yandex_kubernetes_node_group.cpu.name != ""
    error_message = "CPU node group must still be present when GPU is enabled"
  }
}
