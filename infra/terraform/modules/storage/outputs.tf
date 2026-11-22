output "bucket_name" {
  value = yandex_storage_bucket.artifacts.bucket
}

output "bucket_domain_name" {
  value = yandex_storage_bucket.artifacts.bucket_domain_name
}

output "kms_key_id" {
  value = try(yandex_kms_symmetric_key.artifacts[0].id, null)
}

output "private_access_confirmed" {
  description = "Static confirmation that anonymous read/list are disabled in config."
  value       = true
}

output "artifact_key_layout" {
  description = "Recommended object key layout for future uploads (not uploaded in stage 3B)."
  value = {
    onnx         = "models/credit_scoring_nn.onnx"
    preprocessor = "models/preprocessor.joblib"
    metadata     = "models/credit_scoring_nn_metadata.json"
  }
}
