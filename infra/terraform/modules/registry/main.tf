resource "yandex_container_registry" "this" {
  folder_id = var.folder_id
  name      = var.registry_name != "" ? var.registry_name : "${var.name_prefix}-cr"
  labels    = var.labels
}
