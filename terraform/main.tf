# =============================================================================
# AI Civilization Simulator — Multi-Cloud Root Module
#
# Usage:
#   terraform apply -var="target_cloud=azure"
#   terraform apply -var="target_cloud=gcp"
#   terraform apply -var="target_cloud=aws"
#
# Only ONE module's count will be 1; the other two are no-ops.
# =============================================================================

locals {
  # Environment variables injected into the container on every platform.
  # Matches the field names in backend/app/core/config.py (Settings).
  common_env = {
    DB_HOST                      = var.db_host
    DB_PORT                      = var.db_port
    DB_USER                      = var.db_user
    DB_NAME                      = var.db_name
    AZURE_OPENAI_ENDPOINT        = var.azure_openai_endpoint
    AZURE_OPENAI_DEPLOYMENT_NAME = var.azure_openai_deployment_name
    AZURE_OPENAI_API_VERSION     = var.azure_openai_api_version
    AI_ENABLED                   = var.ai_enabled
    APP_ENV                      = "production"
    LOG_LEVEL                    = "INFO"
  }

  # Sensitive env vars are passed separately so Terraform can mark them secret.
  secret_env = {
    DB_PASSWORD       = var.db_password
    AZURE_OPENAI_KEY  = var.azure_openai_key
  }
}

# ---------------------------------------------------------------------------
# Azure Container Apps  (scale-to-zero: min_replicas = 0)
# ---------------------------------------------------------------------------
module "azure" {
  count  = var.target_cloud == "azure" ? 1 : 0
  source = "./modules/azure"

  app_name       = var.app_name
  app_image      = var.app_image
  resource_group = var.azure_resource_group
  location       = var.azure_location
  common_env     = local.common_env
  secret_env     = local.secret_env
}

# ---------------------------------------------------------------------------
# Google Cloud Run  (scale-to-zero: min_instance_count = 0)
# ---------------------------------------------------------------------------
module "gcp" {
  count  = var.target_cloud == "gcp" ? 1 : 0
  source = "./modules/gcp"

  app_name   = var.app_name
  app_image  = var.app_image
  project_id = var.gcp_project_id
  region     = var.gcp_region
  common_env = local.common_env
  secret_env = local.secret_env
}

# ---------------------------------------------------------------------------
# AWS Lambda + Function URL  (scale-to-zero: $0 when idle)
# ---------------------------------------------------------------------------
module "aws" {
  count  = var.target_cloud == "aws" ? 1 : 0
  source = "./modules/aws"

  app_name   = var.app_name
  app_image  = var.app_image
  aws_region = var.aws_region
  common_env = local.common_env
  secret_env = local.secret_env
}
