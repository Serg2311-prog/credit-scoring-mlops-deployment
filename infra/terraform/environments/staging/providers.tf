# Credentials via environment (never commit tokens/keys):
#   YC_TOKEN or YC_SERVICE_ACCOUNT_KEY_FILE
#   YC_CLOUD_ID
#   YC_FOLDER_ID
# Optional: YC_ZONE
provider "yandex" {
  cloud_id  = var.cloud_id
  folder_id = var.folder_id
  zone      = var.zone
}
