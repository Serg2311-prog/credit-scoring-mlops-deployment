output "registry_id" {
  value = yandex_container_registry.this.id
}

output "registry_name" {
  value = yandex_container_registry.this.name
}

output "image_name_examples" {
  description = "Suggested immutable image references (digest preferred over :latest)."
  value = {
    api_tag_template    = "cr.yandex/${yandex_container_registry.this.id}/credit-scoring-api:<git-sha>"
    api_digest_template = "cr.yandex/${yandex_container_registry.this.id}/credit-scoring-api@sha256:<digest>"
    models_tag_template = "cr.yandex/${yandex_container_registry.this.id}/credit-scoring-models:<model-version>"
  }
}
