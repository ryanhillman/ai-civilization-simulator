# =============================================================================
# Azure Container Apps — Scale-to-Zero
#
# Resources created:
#   - Resource Group
#   - Log Analytics Workspace  (required by Container Apps Environment)
#   - Container Apps Environment
#   - Container App  (min_replicas = 0  →  scales to zero when idle)
#
# The app is exposed via an HTTPS ingress managed by ACA.
# Secret env vars are stored as ACA secrets (not in plain env block).
# =============================================================================

resource "azurerm_resource_group" "main" {
  name     = var.resource_group
  location = var.location
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.app_name}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

# ACA secrets block — one entry per sensitive var.
# Referenced by name in the container env block below.
locals {
  aca_secrets = [
    for k, v in var.secret_env : {
      name  = lower(replace(k, "_", "-"))
      value = v
    }
  ]
}

resource "azurerm_container_app" "main" {
  name                         = var.app_name
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  # --- Secrets (sensitive values) ---
  dynamic "secret" {
    for_each = local.aca_secrets
    content {
      name  = secret.value.name
      value = secret.value.value
    }
  }

  template {
    # Scale-to-zero: min = 0, scale up on HTTP traffic.
    min_replicas = 0
    max_replicas = 5

    container {
      name   = "api"
      image  = var.app_image
      cpu    = 0.5
      memory = "1Gi"

      # --- Plain env vars ---
      dynamic "env" {
        for_each = var.common_env
        content {
          name  = env.key
          value = env.value
        }
      }

      # --- Secret refs ---
      dynamic "env" {
        for_each = local.aca_secrets
        content {
          name        = upper(replace(env.value.name, "-", "_"))
          secret_name = env.value.name
        }
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}
