# =============================================================================
# Root variables — shared across all three cloud modules.
# Only populate credentials for the cloud you are targeting.
# =============================================================================

# ---------------------------------------------------------------------------
# Cloud selector
# ---------------------------------------------------------------------------

variable "target_cloud" {
  type        = string
  description = "Which cloud to deploy to: azure | gcp | aws"
  default     = "azure"

  validation {
    condition     = contains(["azure", "gcp", "aws"], var.target_cloud)
    error_message = "target_cloud must be one of: azure, gcp, aws."
  }
}

# ---------------------------------------------------------------------------
# App identity
# ---------------------------------------------------------------------------

variable "app_name" {
  type        = string
  description = "Base name used for all cloud resources."
  default     = "ai-civ-sim"
}

variable "app_image" {
  type        = string
  description = <<-EOT
    Full Docker image URI already pushed to the target cloud's registry.
      Azure : <acr-name>.azurecr.io/ai-civ-sim:<tag>
      GCP   : <region>-docker.pkg.dev/<project>/ai-civ-sim/api:<tag>
      AWS   : <account>.dkr.ecr.<region>.amazonaws.com/ai-civ-sim:<tag>
  EOT
}

# ---------------------------------------------------------------------------
# Database — injected as separate env vars (matches Settings in config.py)
# ---------------------------------------------------------------------------

variable "db_host" {
  type        = string
  description = "PostgreSQL host (managed DB endpoint)."
}

variable "db_port" {
  type        = string
  description = "PostgreSQL port."
  default     = "5432"
}

variable "db_user" {
  type        = string
  description = "PostgreSQL username."
  default     = "civ_user"
}

variable "db_password" {
  type        = string
  description = "PostgreSQL password."
  sensitive   = true
}

variable "db_name" {
  type        = string
  description = "PostgreSQL database name."
  default     = "civ_db"
}

# ---------------------------------------------------------------------------
# Azure OpenAI — optional; app degrades gracefully when ai_enabled = false
# ---------------------------------------------------------------------------

variable "azure_openai_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "azure_openai_endpoint" {
  type    = string
  default = ""
}

variable "azure_openai_deployment_name" {
  type    = string
  default = "gpt-4o"
}

variable "azure_openai_api_version" {
  type    = string
  default = "2024-02-01"
}

variable "ai_enabled" {
  type    = string
  default = "false"
}

# ---------------------------------------------------------------------------
# Azure-specific
# ---------------------------------------------------------------------------

variable "azure_subscription_id" {
  type    = string
  default = ""
}

variable "azure_resource_group" {
  type    = string
  default = "ai-civ-sim-rg"
}

variable "azure_location" {
  type    = string
  default = "eastus"
}

# ---------------------------------------------------------------------------
# GCP-specific
# ---------------------------------------------------------------------------

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_region" {
  type    = string
  default = "us-central1"
}

# ---------------------------------------------------------------------------
# AWS-specific
# ---------------------------------------------------------------------------

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_account_id" {
  type    = string
  default = ""
}
