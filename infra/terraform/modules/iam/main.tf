# Cluster control-plane service account (Managed Kubernetes agent).
resource "yandex_iam_service_account" "k8s_cluster" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-k8s-cluster-sa"
  description = "Managed Kubernetes cluster agent (least privilege)"
}

# Node group service account (pull images, write logs).
resource "yandex_iam_service_account" "k8s_nodes" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-k8s-nodes-sa"
  description = "Kubernetes node group SA (image pull + logging)"
}

# Workload SA for pods that read ML artifacts from Object Storage.
resource "yandex_iam_service_account" "ml_reader" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-ml-reader-sa"
  description = "Read-only access to ML artifact bucket"
}

# CI/CD push SA (registry writer) — no cloud admin.
resource "yandex_iam_service_account" "registry_pusher" {
  folder_id   = var.folder_id
  name        = "${var.name_prefix}-registry-pusher-sa"
  description = "Push container images to Container Registry"
}

locals {
  cluster_roles = concat(
    [
      "k8s.clusters.agent",
      "vpc.publicAdmin",
      "container-registry.images.puller",
      "logging.writer",
    ],
    var.enable_load_balancer_admin ? ["load-balancer.admin"] : []
  )

  node_roles = [
    "container-registry.images.puller",
    "logging.writer",
  ]

  ml_reader_roles = [
    "storage.viewer",
  ]

  registry_pusher_roles = [
    "container-registry.images.pusher",
  ]
}

resource "yandex_resourcemanager_folder_iam_member" "k8s_cluster" {
  for_each = toset(local.cluster_roles)

  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.k8s_cluster.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "k8s_nodes" {
  for_each = toset(local.node_roles)

  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.k8s_nodes.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "ml_reader" {
  for_each = toset(local.ml_reader_roles)

  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.ml_reader.id}"
}

resource "yandex_resourcemanager_folder_iam_member" "registry_pusher" {
  for_each = toset(local.registry_pusher_roles)

  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.registry_pusher.id}"
}
