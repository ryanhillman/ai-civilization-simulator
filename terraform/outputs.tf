# =============================================================================
# Cloud-agnostic output — the same variable name regardless of target cloud.
# After `terraform apply`, run: terraform output app_url
# =============================================================================

output "app_url" {
  description = "Public HTTPS endpoint of the deployed application."
  value = (
    var.target_cloud == "azure" ? module.azure[0].app_url :
    var.target_cloud == "gcp"   ? module.gcp[0].app_url   :
                                  module.aws[0].app_url
  )
}

output "target_cloud" {
  description = "The cloud this deployment targets."
  value       = var.target_cloud
}
