locals {
  labels = merge(var.labels, {
    environment = var.environment
    purpose     = "credit-scoring-observability"
  })
  # yandex_logging_group.retention_period is a duration string (e.g. "168h").
  retention_period = "${var.log_retention_days * 24}h"
}

# Cloud Logging group for Managed Kubernetes master logs and future app logs.
# Does NOT scrape Prometheus /metrics by itself — that requires a separate
# Prometheus/VMAgent or Yandex Monitoring agent integration (future stage).
resource "yandex_logging_group" "k8s" {
  folder_id        = var.folder_id
  name             = "${var.name_prefix}-logs"
  description      = "Credit scoring logs (${var.environment}); no PII/financial payloads"
  retention_period = local.retention_period
  labels           = local.labels
}
