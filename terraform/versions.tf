terraform {
  required_version = ">= 1.7"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Uncomment and configure a remote backend for team usage.
  # backend "azurerm" { ... }
  # backend "gcs"     { ... }
  # backend "s3"      { ... }
}

# ---------------------------------------------------------------------------
# Provider blocks — only the target cloud's credentials are needed.
# The other two providers are declared but will have no resources to manage
# (their module count = 0), so they make zero API calls.
# ---------------------------------------------------------------------------

provider "azurerm" {
  features {}
  subscription_id         = var.azure_subscription_id
  skip_provider_registration = true
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

provider "aws" {
  region = var.aws_region
}
