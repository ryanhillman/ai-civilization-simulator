output "app_url" {
  description = "HTTPS URL of the Azure Container App."
  value       = "https://${azurerm_container_app.main.latest_revision_fqdn}"
}
