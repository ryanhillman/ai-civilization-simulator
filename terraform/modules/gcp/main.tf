# =============================================================================
# Google Cloud Run v2 — Scale-to-Zero
#
# Resources created:
#   - Secret Manager secrets  (one per sensitive var)
#   - Cloud Run v2 Service    (min_instance_count = 0  →  scales to zero)
#   - IAM binding             (allUsers invoker — public endpoint)
#
# Required APIs (enable once per project):
#   gcloud services enable run.googleapis.com secretmanager.googleapis.com
# =============================================================================

# --- Secret Manager: store sensitive env vars securely ---
resource "google_secret_manager_secret" "secrets" {
  for_each  = var.secret_env
  project   = var.project_id
  secret_id = "${var.app_name}-${lower(replace(each.key, "_", "-"))}"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "secrets" {
  for_each    = var.secret_env
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value
}

# Grant Cloud Run's service account access to read the secrets.
resource "google_secret_manager_secret_iam_member" "run_access" {
  for_each  = var.secret_env
  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

data "google_project" "project" {
  project_id = var.project_id
}

# --- Cloud Run v2 Service ---
resource "google_cloud_run_v2_service" "main" {
  name     = var.app_name
  location = var.region
  project  = var.project_id
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0   # scale-to-zero
      max_instance_count = 5
    }

    containers {
      image = var.app_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true  # only bill for CPU during request processing
      }

      # Plain env vars
      dynamic "env" {
        for_each = var.common_env
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secret env vars — sourced from Secret Manager
      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.secrets[env.key].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_version.secrets]
}

# --- Public access (unauthenticated invocations) ---
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.main.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
