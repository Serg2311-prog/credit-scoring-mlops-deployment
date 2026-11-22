output "log_group_id" {
  value = yandex_logging_group.k8s.id
}

output "log_group_name" {
  value = yandex_logging_group.k8s.name
}

output "metrics_integration_notes" {
  description = "Honest limitations for /metrics scraping."
  value = {
    api_endpoint_ready        = "FastAPI exposes /metrics (Prometheus text)"
    k8s_service_annotations   = "prometheus.io/scrape|port|path already on stage-3A Service"
    yandex_monitoring_auto    = false
    required_future_component = "Prometheus Operator / VMAgent / Yandex Monitoring agent scrape config"
    alerting_examples = [
      "API readiness < 1 for 5m",
      "HTTP 5xx rate > threshold",
      "Inference latency p95 regression",
    ]
    log_policy = "JSON logs without client financial features / PII"
  }
}
